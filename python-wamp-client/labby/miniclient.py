from autobahn.asyncio.wamp import ApplicationRunner
from autobahn.asyncio.wamp import ApplicationSession
import asyncio

DEFAULT_COORDINATOR = True
class MiniClient(ApplicationSession):
    def __init__(self, config):
        self.username = config.extra.get('username')
        self.extra = config.extra
        print(f"creating MiniClient\nconfig: {config}")
        super().__init__(config=config)

    def onConnect(self):
        if(DEFAULT_COORDINATOR):
            self.join(self.config.realm)
        else:
            self.join(self.config.realm, ['ticket'],
                 authid = f'client/{self.username}')

    async def onJoin(self, details):
        print(f"MiniClient for {self.username} ready")
        func = self.extra.get('func')
        args = self.extra.get('args')
        kwargs = self.extra.get('kwargs')
        ret = await func(*args, **kwargs)
        loopres = asyncio.get_event_loop().create_future()
        loopres.set_result(ret)
        self.leave()
        return ret

    def onLeave(self, details):
        print(f"MiniClient for {self.username} leaving")
        self.disconnect()
        asyncio.get_event_loop().stop()

from autobahn.twisted.component import Component

backend_url = "ws://localhost:20408/ws" #context.frontend.backend_url
backend_realm = "realm1" #context.frontend.backend_realm

def userClient(func):
    async def wrapper(*args, **kwargs):
        context = kwargs.get("context")
        if not context: context = args[0]

        username =kwargs.get("username")
        if not username: username = args[1]

        # TODO: static parameter
        def run_mc():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            #create miniclient with username
            mc_runner = ApplicationRunner(backend_url, realm=backend_realm,
                                          extra={'username': username, 'func': func, 'args': args, 'kwargs': kwargs})
            mc_coro = mc_runner.run(MiniClient, start_loop=False)

            a = loop.run_until_complete(mc_coro)
            b = loop.run_forever()
            print("inner loop is done")

        loop = asyncio.get_event_loop()
        ret = await loop.run_in_executor(None, run_mc)

        print("done, finishing up")
        return ret

    return wrapper

@userClient
async def test_function(context="a", username="user"):
    print("Hallo")
    return "Ohne mich ist alles doof"

async def run_function():
    res = await test_function("a", "b")
    print(f"overall result: {res}")

if __name__ == "__main__":
    asyncio.run(run_function())
