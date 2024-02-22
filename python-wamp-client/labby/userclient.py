from autobahn.asyncio.wamp import ApplicationRunner
from .labby_types import Session
import asyncio

class UserClientSession(Session):
    default_coordinator = None
    backend_url = None
    backend_realm = None

    @staticmethod
    def set_classvariables(default_coordinator, backend_url, backend_realm):
        UserClientSession.default_coordinator = default_coordinator
        UserClientSession.backend_url = backend_url
        UserClientSession.backend_realm = backend_realm

    def __init__(self, config):
        self.username   = config.extra.get('username')
        self.context    = config.extra.get('context')
        self.extra = config.extra
        super().__init__(config=config)

    def onConnect(self):
        try:
            if(UserClientSession.default_coordinator):
                self.join(self.config.realm)
            else:
                self.join(self.config.realm, ['ticket'],
                     authid = f'client/{self.username}')
        except Exception as ex:
            print(ex)

    def onChallenge(self, challenge):
        if not self.default_coordinator:
            self.log.info("Authencticating.")
            if challenge.method == 'ticket':
                return ""  # don't provide a password
            self.log.error(
                "Only Ticket authentication enabled, atm. Aborting...")
            raise NotImplementedError(
                "Only Ticket authentication enabled, atm")
        else:
            pass

    async def onJoin(self, details):
        callstring = self.extra.get('callstring')
        args = self.extra.get('args')
        ret = await self.call(callstring, *args)

        self.context.log.info(f"Userclient for {self.username} calling {callstring} {args}")
        self.leave()
        self.extra.get("future_result").set_result(ret)

    def onLeave(self, details):
        self.context.log.info(f"UserClient for {self.username} out")
        self.disconnect()

async def call_in_userclient(context, username, callstring, *args):
    future_result = asyncio.get_running_loop().create_future()
    mc_runner = ApplicationRunner(UserClientSession.backend_url, realm=UserClientSession.backend_realm,
                                  extra={'context':         context,    'username': username,
                                         'callstring':      callstring, 'args': args,
                                         'future_result':   future_result})
    mc_coro = mc_runner.run(UserClientSession, start_loop=False)
    await asyncio.gather(mc_coro, future_result)
    return future_result.result()
