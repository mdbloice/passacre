import json
import os

from twisted.internet import protocol
from twisted.protocols import amp
from twisted.python import log

from passacre.agent import commands


try:
    from passacre.agent import pencrypt
except ImportError:
    pencrypt = None


class PassacreAgentServerProtocol(amp.AMP):
    def __init__(self, factory, app):
        amp.AMP.__init__(self)
        self.factory = factory
        self.app = app

    @commands.Unlock.responder
    def unlock(self, password):
        if self.factory.password is not None:
            raise commands.AgentUnlocked()
        self.factory.password = password
        self.factory.load_sites()
        return {}

    @commands.Lock.responder
    def lock(self):
        if self.factory.password is None:
            raise commands.AgentLocked()
        self.factory.password = None
        self.factory.sites = set()
        return {}

    @commands.Generate.responder
    def generate(self, site, username=None, password=None, save_site=False):
        if password is None:
            password = self.factory.password
        if password is None:
            raise commands.AgentLocked()
        generated = self.app.config.generate_for_site(
            username, password, site)
        if save_site and self.factory.password is not None:
            self.factory.sites.add(site)
            self.factory.save_sites()
        return {'password': generated}

    @commands.FetchSiteList.responder
    def fetch_site_list(self):
        if self.factory.password is None:
            raise commands.AgentLocked()
        return {'sites': list(self.factory.sites)}


class PassacreAgentServerFactory(protocol.Factory):
    protocol = PassacreAgentServerProtocol

    def __init__(self, app):
        self.app = app
        self.password = None
        self.sites = set()

    def build_box(self):
        if pencrypt is None:
            raise commands.SiteListUnavailable()
        if self.password is None:
            raise commands.AgentLocked()
        return pencrypt.box_of_config_and_password(self.app.config, self.password)

    def sites_file(self):
        return pencrypt.EncryptedFile(
            self.build_box(),
            os.path.expanduser('~/.config/passacre/sites'))

    def load_sites(self):
        try:
            fobj = self.sites_file()
            data = fobj.read()
            self.sites.update(json.loads(data.decode()))
        except Exception:
            log.err(None, 'error loading sites file')

    def save_sites(self):
        fobj = self.sites_file()
        fobj.write(json.dumps(list(self.sites)).encode())

    def buildProtocol(self, addr):
        return self.protocol(self, self.app)
