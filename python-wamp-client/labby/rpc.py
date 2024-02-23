"""
Generic RPC functions for labby
"""

# import asyncio
import asyncio
from cgi import print_exception
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Type, Union

import yaml
from attr import attrib, attrs
from autobahn.wamp.exception import ApplicationError
from labby.console import Console

from labby.resource import LabbyResource, NetworkSerialPort, PowerAction, power_resources, power_resource_from_name

from .labby_error import (LabbyError, failed, invalid_parameter,
                          not_found)
from .labby_types import (ExporterName, GroupName, LabbyPlace, PlaceName, PowerState, Resource,
                          ResourceName, Session, Place)
from .labby_util import flatten
from .userclient import call_in_userclient

def _check_not_none(*args, **kwargs) -> Optional[LabbyError]:
    return next((invalid_parameter(f"Missing required parameter: {name}.") for name, val in vars().items() if val is None), None)


@attrs()
class RPCDesc():
    name: str = attrib(default=None)
    endpoint: str = attrib(default=None)
    remote_endpoint: str = attrib(default=None)
    info: Optional[str] = attrib(default=None)
    parameter: Optional[List[Dict[str, str]]] = attrib(default=None)
    return_type: Optional[str] = attrib(default=None)


def _localfile(path):
    return Path(os.path.dirname(os.path.realpath(__file__))).joinpath(path)


FUNCTION_INFO = {}
with open(_localfile('rpc_desc.yaml'), 'r', encoding='utf-8') as file:
    FUNCTION_INFO = {key: RPCDesc(**val) for key, val in yaml.load(file,
                                                                   yaml.loader.FullLoader).items() if val is not None}


# non exhaustive list of serializable primitive types
_serializable_primitive: List[Type] = [int, float, str, bool]


def invalidates_cache(attribute, *rec_args, reconstitute: Optional[Callable] = None):
    """
    on call clear attribute (e.g. set to None)
    """
    def decorator(func: Callable):
        def wrapped(self: Session, *args, **kwargs):
            setattr(self, attribute, None)
            return func(self, *args, **kwargs)
        return wrapped
    return decorator


def cached(attribute: str):
    """
    Decorator defintion to cache data in labby context and fetch data from server
    """
    assert attribute is not None

    def decorator(func: Callable):

        async def wrapped(context: Session, *args, **kwargs):
            assert context is not None

            if not hasattr(context, attribute):
                context.__dict__.update({attribute: None})
                data = None
            else:
                data: Optional[Dict] = context.__getattribute__(
                    attribute)
            if data is None:
                data: Optional[Dict] = await func(context, *args, **kwargs)
                if not isinstance(data, LabbyError):
                    context.__setattr__(attribute, data)
            return data

        return wrapped

    return decorator


def labby_serialized(func):
    """
    Custom serializer decorator for labby rpc functions
    to make sure returned values are cbor/json serializable
    """
    async def wrapped(*args, **kwargs) -> Union[None, List, Dict, int, float, str, bool]:
        ret = await func(*args, **kwargs)
        if ret is None:
            return None
        if isinstance(ret, LabbyError):
            return ret.to_json()
        if isinstance(ret, LabbyPlace):
            return ret.to_json()
        if isinstance(ret, (dict, list)) or type(ret) in _serializable_primitive:
            return ret
        raise NotImplementedError(
            f"{type(ret)} can currently not be serialized!")

    return wrapped


async def call_coordinator(context: Session, callstring: str, *args, **kwargs) -> Any:
    if not args: args = []
    fullstring = f"{callstring} {' '.join(args)} {kwargs}"

    try:
        if username := kwargs.get('username'):
            res = await call_in_userclient(context, username, callstring, *args)
        else:
            context.log.info(f"calling coordinator {fullstring}")
            res = await context.call(callstring, *args)

        context.log.info("received answer for {}: {}".format(fullstring, res))
        return res
    except ApplicationError as err:
        return failed(f"Got exception while trying to call {fullstring}: {err}")


async def fetch(context: Session, attribute: str, endpoint: str, *args, **kwargs) -> Any:
    """
    QoL function to fetch data drom Coordinator and store in attribute member in Session
    """
    assert context is not None
    assert attribute is not None
    assert endpoint is not None

    data: Optional[Dict] = getattr(context, attribute)
    if data is None:
        data: Optional[Dict] = await call_coordinator(context, endpoint, *args, **kwargs)
        setattr(context, attribute, data)
    return data


async def fetch_places(context: Session,
                       place: Optional[PlaceName]) -> Union[Dict[PlaceName, Place], LabbyError]:
    """
    Fetch places from coordinator, update if missing and handle possible errors
    """
    assert context is not None

    _data = await context.places.get(context)  # type: ignore
    if _data is None:
        if place is None:
            return not_found("Could not find any places.")
        return not_found(f"Could not find place with name {place}.")
    if place is not None:
        if place in _data.keys():
            return {place: _data[place]}
        return not_found(f"Could not find place with name {place}.")
    return _data


async def fetch_resources(context: Session,
                          place: Optional[PlaceName],
                          resource_key: Optional[ResourceName]) -> Union[Dict, LabbyError]:
    """
    Fetch resources from coordinator, update if missing and handle possible errors
    """
    assert context is not None
    data: Optional[Dict] = await context.resources.get(context)
    if data is None:
        if place is None:
            return not_found("Could not find any resources.")
        return not_found(f"No resources found for place {place}.")

    if place is not None:
        data = {exporter: {k: v for k, v in exporter_data.items() if k == place and v}
                for exporter, exporter_data in data.items()}

    if resource_key is not None:
        data = {exporter:
                {place_name:
                    {k: v for k, v in place_res.items() if k == resource_key if v}
                    for place_name, place_res in exporter_data.items() if place_res}
                for exporter, exporter_data in data.items()}
    return data


@cached("peers")
async def fetch_peers(context: Session) -> Union[Dict, LabbyError]:
    session_ids = await context.call("wamp.session.list")
    sessions = {}
    for sess in session_ids:  # ['exact']:
        tmp = await context.call("wamp.session.get", sess)
        if tmp and 'authid' in tmp:
            sessions[tmp['authid']] = tmp
    return sessions


async def get_exporters(context: Session) -> Union[List[ExporterName], LabbyError]:
    peers = await fetch_peers(context)
    if isinstance(peers, LabbyError):
        return peers
    assert peers is not None
    return [x.replace('exporter/', '') for x in peers if x.startswith('exporter')]


def _calc_power_for_place(place_name, resources: Iterable[Dict]):
    pstate = False
    for res in resources:
        if isinstance(res['acquired'], Iterable):
            pstate |= place_name in res['acquired']
        else:
            pstate |= res['acquired'] == place_name
    return pstate


@cached("power_states")
async def fetch_power_state(context: Session,
                            place: Optional[PlaceName]) -> Union[PowerState, LabbyError]:
    """
    Use fetch resource to determine power state, this may update context.resource
    """

    _resources = await fetch_resources(context=context, place=place, resource_key=None)
    if isinstance(_resources, LabbyError):
        return _resources
    if len(_resources) > 0:
        _resources = flatten(_resources)
    _places = await fetch_places(context, place)
    if isinstance(_places, LabbyError):
        return _places
    power_states = {}
#    assert _places
    for place_name, place_data in _places.items():
        if 'acquired_resources' in place_data:
            if len(place_data['acquired_resources']) == 0 or place_name not in _resources:
                power_states[place_name] = {'power_state': False}
                continue
            resources_to_check = ((v for k, v in _resources[place_name].items() if any(
                (k in a for a in place_data['acquired_resources']))))
            power_states[place_name] = {
                'power_state': _calc_power_for_place(place_name, resources_to_check)}
    return power_states


@labby_serialized
async def places(context: Session,
                 place: Optional[PlaceName] = None) -> Union[List[LabbyPlace], LabbyError]:
    """
    returns registered places as dict of lists
    """
    context.log.info("Fetching places.")

    data = await fetch_places(context, place)
    if isinstance(data, LabbyError):
        return data
    power_states = await fetch_power_state(context=context, place=place)
    assert power_states is not None
    if isinstance(power_states, LabbyError):
        return power_states
    await get_reservations(context)

    def token_from_place(name):
        return next((token for token, x in context.reservations.items()
                     if x['filters']['main']['name'] == name), None)
    place_res = []
#    assert data
    for place_name, place_data in data.items():
        # append the place to acquired places if
        # it has been acquired in a previous session
        if (place_data and place_data['acquired'] == context.user_name
                and place_name not in context.acquired_places
                ):
            context.acquired_places.add(place_name)
        if place is not None and place_name != place:
            continue
        # ??? (Kevin) what if there are more than one or no matches
        if len(place_data["matches"]) > 0 and 'exporter' in place_data["matches"]:
            exporter = place_data["matches"][0]["exporter"]
        else:
            exporter = None

        place_data.update({
            "name": place_name,
            "exporter": exporter,
            "power_state": power_states.get(place_name, {}).get('power_state', None),
            "reservation": token_from_place(place_name)
        })
        place_res.append(place_data)
    return place_res


@labby_serialized
async def list_places(context: Session) -> List[PlaceName]:
    """
    Return all place names
    """
    await fetch_places(context, None)
    return list(context.places.get_soft().keys()) if context.places else []


@labby_serialized
async def resource(context: Session,
                   place: Optional[PlaceName] = None,
                   resource_key=None
                   ) -> Union[Dict[ResourceName, Resource], LabbyError]:
    """
    rpc: returns resources registered for given place
    """
    context.log.info(f"Fetching resources for {place}.")
    resource_data = await fetch_resources(context=context, place=place, resource_key=resource_key)

    if isinstance(resource_data, LabbyError):
        return resource_data

    if place is None:
        return resource_data
    if len(flatten(resource_data)) == 0:
        return not_found(f"Place {place} not found.")
    return resource_data


@labby_serialized
async def power_state(context: Session,
                      place: PlaceName,
                      ) -> Union[PowerState, LabbyError]:
    """
    rpc: return power state for a given place
    """
    if place is None:
        return invalid_parameter("Missing required parameter: place.").to_json()
    power_data = await fetch_power_state(context=context, place=place)
    assert power_data is not None
    if isinstance(power_data, LabbyError):
        return power_data

    if place not in power_data.keys():
        return not_found(f"Place {place} not found on Coordinator.").to_json()

    return power_data[place]


@labby_serialized
async def resource_overview(context: Session,
                            place: Optional[PlaceName] = None,
                            ) -> Union[List[Resource], LabbyError]:
    """
    rpc: returns list of all resources on target
    """
    context.log.info(f"Fetching resources overview for {place}.")

    targets = await fetch_resources(context=context, place=place, resource_key=None)
    if isinstance(targets, LabbyError):
        return targets

    ret = []
    for exporter, resources in targets.items():
        for res_place, res in resources.items():
            if place is None or place == res_place:
                ret.extend({'name': key, 'target': exporter,
                            'place': res_place, **values} for key, values in res.items())
    return ret


@labby_serialized
async def resource_by_name(context: Session,
                           name: ResourceName,  # filter by name
                           ) -> Union[List[Resource], LabbyError]:
    """
    rpc: returns list of all resources of given name on target
    """

    if name is None:
        return invalid_parameter("Missing required parameter: name.")

    resource_data = await fetch_resources(context, place=None, resource_key=None)
    if isinstance(resource_data, LabbyError):
        return resource_data

    ret = []
    for target, resources in resource_data.items():
        for place, res in resources.items():
            ret.extend(
                {'name': key, 'target': target, 'place': place, **values}
                for key, values in res.items()
                if name == key
            )

    return ret


@labby_serialized
async def resource_names(context: Session) -> List[Dict[str, str]]:
    await fetch_resources(context, None, None)
    data = context.resources or {}
    def it(x): return x.items()
    return [
        {'exporter': exporter,
         'group': grp_name,
         'class': x.get('cls'),
         'name': name,
         }
        for exporter, group in it(data) for grp_name, res in it(group) for name, x in it(res)
    ]


@labby_serialized
async def acquire(context: Session,
                  place: PlaceName,
                  username: str  # used by @run_in_user_client
                  # userclient=None   # set  in @run_in_user_client
                 ) -> Union[bool, LabbyError]:
    """
    rpc for acquiring places
    """
    context.log.debug(f"about to acquire {place} for {username}")
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    if place in context.acquired_places:
        return failed(f"Already acquired place {place}.")

    # , group, resource_key, place)
    context.log.info(f"Acquiring place {place}.")
    acquire_successful = await call_coordinator(context, "org.labgrid.coordinator.acquire_place", place, username=username)
    if acquire_successful:
        context.acquired_places.add(place)
        # remove the reservation if there was one
        if token := next((token for token, x in context.reservations.items() if x['filters']['main']['name'] == place), None,):
            ret = await cancel_reservation(context, token)
            if isinstance(ret, LabbyError):
                # context.log.error(f"Could not cancel reservation after acquire: {ret}")
                print(f"Could not cancel reservation after acquire: {ret}")
            del context.reservations[token]
    return acquire_successful


@labby_serialized
async def release(context: Session,
                  place: PlaceName) -> Union[bool, LabbyError]:
    """
    rpc for releasing 'acquired' places
    """
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    # if place not in context.acquired_places:
    #     return failed(f"Place {place} is not acquired")
    context.log.info(f"Releasing place {place}.")
    release_successful = await call_coordinator(context,'org.labgrid.coordinator.release_place', place)
    if place in context.acquired_places:  # place update was quicker
        context.acquired_places.remove(place)
    return release_successful


@labby_serialized
async def info(_context=None, func_key: Optional[str] = None) -> Union[List[Dict], LabbyError]:
    """
    RPC call for general info for RPC function usage
    """
    if func_key is None:
        return [desc.__dict__ for desc in globals()["FUNCTION_INFO"].values()]
    if func_key not in globals()["FUNCTION_INFO"]:
        return not_found(f"Function {func_key} not found in registry.")
    return globals()["FUNCTION_INFO"][func_key].__dict__


async def get_reservations(context: Session) -> Dict:
    """
    RPC call to list current reservations on the Coordinator
    """
    reservation_data: Dict = await call_coordinator(context, "org.labgrid.coordinator.get_reservations")

    for token, data in reservation_data.items():
        if (data['state'] in ('waiting', 'allocated', 'acquired')
                and data['owner'] == context.user_name):
            context.to_refresh.add(token)
    context.reservations.update(**reservation_data)
    return reservation_data


@labby_serialized
async def create_reservation(context: Session, place: PlaceName, username="", priority: float = 0.) -> Union[Dict, LabbyError]:
    # TODO figure out filters, priorities, etc
    # TODO should multiple reservations be allowed?
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    await get_reservations(context)  # get current state from coordinator
    if any((place == x['filters']['main']['name'] for x in context.reservations.values() if 'name' in x['filters']['main'] and x['state'] not in ('expired', 'invalid'))):
        return failed(f"Place {place} is already reserved.")
    reservation = await call_coordinator(context, "org.labgrid.coordinator.create_reservation",
                                     f"name={place}",
                                     prio=priority, username=username)
    if not reservation:
        return failed("Failed to create reservation")
    context.reservations.update(reservation)
    context.to_refresh.add((next(iter(reservation.keys()))))
    return reservation


async def refresh_reservations(context: Session):
    while True:
        to_remove = set()
        context.reservations = await call_coordinator(context, "org.labgrid.coordinator.get_reservations")
        for token in context.to_refresh:
            if token in context.reservations:
                # context.log.info(f"Refreshing reservation {token}")
                state = context.reservations[token]['state']
                place_name = context.reservations[token]['filters']['main']['name']
                if state == 'waiting':
                    ret = await call_coordinator(context, "org.labgrid.coordinator.poll_reservation", token)
                    if not ret:
                        context.log.error(
                            f"Failed to poll reservation {token}.")
                    context.reservations[token] = ret
                # acquire the resource, when it has been allocated by the coordinator
                elif (context.reservations[token]['state'] == 'allocated'
                      or (context.reservations[token]['state'] == 'acquired' and place_name not in context.acquired_places)
                      ):
                    ret = await acquire(context, place_name, context.reservations[token].get('owner'))
                    await cancel_reservation(context, place_name)
                    if not ret:
                        context.log.error(
                            f"Could not acquire reserved place {token}: {place_name}")
                    to_remove.add(token)
                else:
                    to_remove.add(token)
            else:
                to_remove.add(token)
        for token in to_remove:
            context.to_refresh.remove(token)
        await asyncio.sleep(10.)  # !! TODO set to 10s


@labby_serialized
async def cancel_reservation(context: Session, place: PlaceName) -> Union[bool, LabbyError]:
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    await get_reservations(context)  # get current state from coordinator
    token = next((token for token, x in context.reservations.items()
                 if x['filters']['main']['name'] == place), None)
    if token is None:
        return failed(f"No reservations available for place {place}.")
    del context.reservations[token]
    return await call_coordinator(context,"org.labgrid.coordinator.cancel_reservation", token)


@labby_serialized
async def poll_reservation(context: Session, place: PlaceName) -> Union[Dict, LabbyError]:
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    token = next((token for token, x in context.reservations.items()
                 if x['filters']['main']['name'] == place), None)
    if token is None:
        return failed(f"No reservations available for place {place}.")
    if not token:
        return failed("Failed to poll reservation.")
    reservation = await call_coordinator(context,"org.labgrid.coordinator.poll_reservation", token)
    context.reservations[token] = reservation
    return reservation


@labby_serialized
async def reset(context: Session, place: PlaceName) -> Union[bool, LabbyError]:
    """
    Send a reset request to a place matching a given place name
    Note
    """
    check = _check_not_none()
    if isinstance(check, LabbyError):
        return check
    context.log.info(f"Resetting place {place}")
    release_later = False
    if place not in context.acquired_places:
        release_later = True
        acq = await acquire(context, place, "tmp/reset")
        if isinstance(acquire, LabbyError):
            return acq
        if not acq:
            return failed(f"Could not acquire place {place}.")

    res = await fetch_resources(context, place, None)
    if isinstance(res, LabbyError):
        return failed(f"Failed to get resources for place {place}.")
    res = flatten(res, 2)  # remove exporter and group from res
    for resname, resdata in res.items():
        if resname in power_resources:
            try:
                context.log.info(f"Resetting {place}/{resname}.")
                power_resource = power_resource_from_name(resname, resdata)
                url = power_resource.power(PowerAction.cycle)
                assert (ssh_session := context.ssh_session) is not None
                assert ssh_session.client
                (_, _, serr) = ssh_session.client.exec_command(
                    command=f"curl -Ss '{url}' > /dev/null"
                )
                if len(msg := serr.read()) > 0:
                    context.log.error(
                        f"Got error while resetting console. {msg}")
            except ValueError:
                pass  # not a valid powerresource after all ??
            except Exception as e:
                raise e  # other errors occured o.O

    if release_later:
        rel = await release(context, place)
        if isinstance(rel, LabbyError) or not rel:
            return failed(f"Failed to release place {place} after reset.")
    return True


@labby_serialized
async def console(context: Session, place: PlaceName):
    # TODO allow selection of resource to connect console to
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    # if place not in context.acquired_places:
    #     ret = await acquire(context, place, 'tmp/console')
    #     if isinstance(ret, LabbyError):
    #         return ret
    #     if not ret:
    #         return failed("Failed to acquire Place (It may already have been acquired).")
    if place in context.open_consoles:
        return failed(f"There is already a console open for {place}.")
    # check that place has a console
    _resources = await fetch_resources(context, place, resource_key=None)
    if isinstance(_resources, LabbyError):
        return _resources
    if len(_resources) == 0:
        return failed(f"No resources on {place}.")
    _resources = flatten(_resources, depth=2)  # remove exporter and place
    _resource: Optional[LabbyResource] = next(
        (
            NetworkSerialPort(
                cls=data['cls'],
                port=data['params']['port'],
                host=data['params']['host'],
                speed=data['params']['speed'],
                protocol=data['params'].get('protocol', 'rfc2217'),
            )
            for _, data in _resources.items()
            if 'cls' in data and data['cls'] == 'NetworkSerialPort'
        ),
        None,
    )
    if _resource is None:
        return failed(f"No network serial port on {place}.")
    assert isinstance(_resource, NetworkSerialPort)
    assert context.ssh_session.client
    context.open_consoles[place] = (_con := Console(host=_resource.host or 'localhost',
                                                    speed=_resource.speed,
                                                    port=_resource.port,
                                                    ssh_session=context.ssh_session.client))

    async def _read(read_fn,):
        while place in context.open_consoles:
            try:
                data = await read_fn()
                assert context.frontend
                context.frontend.publish(f"localhost.consoles.{place}", data)
            except (OSError, EOFError):
                print_exception()
                context.log.error(f"Console closed read on {place}.")
                _con.close()
                if place in context.open_consoles:
                    del context.open_consoles[place]
                    print("Closing read.")
            except:
                print_exception()
                context.log.error(f"Console on {place} read failed.")
                _con.close()
                if place in context.open_consoles:
                    del context.open_consoles[place]
                    print("Closing read exc.")
    asyncio.run_coroutine_threadsafe(
        _read(_con.read_stdout), asyncio.get_event_loop())
    asyncio.run_coroutine_threadsafe(
        _read(_con.read_stderr), asyncio.get_event_loop())
    return True


@labby_serialized
async def console_write(context: Session, place: PlaceName, data: str) -> Union[bool, LabbyError]:
    # TODO implement
    if place not in context.acquired_places:
        return failed(f"Place {place} is not acquired.")
    if not (_console := context.open_consoles.get(place)):
        return failed(f"Place {place} has no open consoles.")
    if not data:
        # data was empty
        return failed(f"Could not write to Console {place}. Data was empty")
    try:
        _console.write_to_stdin(data)
    except Exception as e:
        context.log.exception(e)
        return failed(f"Failed to write to Console {place}.")
    #
    # do stuff
    #
    context.log.info(f"Console on {place} received: {data}.")
    return True


@labby_serialized
async def console_close(context: Session, place: PlaceName) -> Optional[LabbyError]:
    if place not in context.acquired_places:
        return failed(f"Place {place} is not acquired.")
    if not context.open_consoles.get(place):
        return failed(f"Place {place} has no open consoles.")
    context.log.info(f"Closing console on {place}.")
    context.open_consoles[place].close()
    del context.open_consoles[place]


async def video(context: Session, *args):
    pass


@labby_serialized
async def forward(context: Session, *args):
    """
    Forward a rpc call to the labgrid coordinator
    """
    return await context.call(*args)


@labby_serialized
async def create_place(context: Session, place: PlaceName) -> Union[bool, LabbyError]:
    """
    Create a new place on the coordinator
    """
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    _places = await fetch_places(context, place=None)
    if isinstance(_places, LabbyError):
        return _places
#    assert _places
    if place in _places:
        return failed(f"Place {place} already exists.")
    return await call_coordinator(context,"org.labgrid.coordinator.add_place", place)


@labby_serialized
async def delete_place(context: Session, place: PlaceName) -> Union[bool, LabbyError]:
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    _places = await fetch_places(context, place)
    assert context.places  # should have been set with fetch_places
    if isinstance(_places, LabbyError):
        return _places
    return await call_coordinator(context, "org.labgrid.coordinator.del_place", place)


@labby_serialized
async def create_resource(context: Session, group_name: GroupName, resource_name: ResourceName) -> Union[bool, LabbyError]:
    # TODO (Kevin) Find a way to do this without being a exporter/ delegate to exporter
    if group_name is None:
        return invalid_parameter("Missing required parameter: group_name.")
    if resource_name is None:
        return invalid_parameter("Missing required parameter: resource_name.")
    ret = await call_coordinator(context, "org.labgrid.coordinator.set_resource", group_name, resource_name, {})
    return ret


@labby_serialized
async def delete_resource(context: Session, group_name: GroupName, resource_name: ResourceName) -> Union[bool, LabbyError]:
    # TODO (Kevin) Find a way to do this without being a exporter/ delegate to exporter
    if group_name is None:
        return invalid_parameter("Missing required parameter: group_name.")
    if resource_name is None:
        return invalid_parameter("Missing required parameter: resource_name.")
    ret = await context.call("org.labgrid.coordinator.update_resource", group_name, resource_name, None)
    return ret


@labby_serialized
async def places_names(context: Session) -> Union[List[PlaceName], LabbyError]:
    _places = await fetch_places(context, None)
    if isinstance(_places, LabbyError):
        return _places
    # assert _places
    return list(_places.keys())


@labby_serialized
async def get_alias(context: Session, place: PlaceName) -> Union[List[str], LabbyError]:
    if place is None:
        return invalid_parameter("Missing required parameter: place.")
    data = await fetch_places(context, place)
    if isinstance(data, LabbyError):
        return data
    assert data
    if len(data) == 0:
        return []
    return [a for x in data.values() for a in x['aliases']]


@labby_serialized
async def add_match(context: Session,
                    place: PlaceName,
                    exporter: ExporterName,
                    group: GroupName,
                    cls: ResourceName,
                    name: ResourceName) -> Union[bool, LabbyError]:
    _check_not_none(**vars())
    try:
        return await context.call("org.labgrid.coordinator.add_place_match", place, f"{exporter}/{group}/{cls}/{name}")
    except:
        return failed(f"Failed to add match {exporter}/{group}/{cls}/{name} to place {place}.")


@labby_serialized
async def del_match(context: Session,
                    place: PlaceName,
                    exporter: ExporterName,
                    group: GroupName,
                    cls: ResourceName,
                    name: ResourceName) -> Union[bool, LabbyError]:
    _check_not_none(**vars())
    try:
        return await context.call("org.labgrid.coordinator.del_place_match", place, f"{exporter}/{group}/{cls}/{name}")
    except:
        return failed(f"Failed to add match {exporter}/{group}/{cls}/{name} to place {place}.")


@labby_serialized
async def acquire_resource(context: Session,
                           place_name: PlaceName,
                           exporter: ExporterName,
                           group_name: GroupName,
                           resource_name: ResourceName) -> Union[bool, LabbyError]:
    _check_not_none(**vars())
    try:
        procedure = f"org.labgrid.exporter.{exporter}.acquire"
        return await context.call(procedure, group_name, resource_name, place_name)
    except:
        return failed(f"Failed to acquire resource {exporter}/{place_name}/{resource_name}.")


@labby_serialized
async def release_resource(context: Session,
                           place_name: PlaceName,
                           exporter: ExporterName,
                           group_name: GroupName,
                           resource_name: ResourceName) -> Union[bool, LabbyError]:
    _check_not_none(**vars())
    try:
        procedure = f"org.labgrid.exporter.{exporter}.release"
        return await context.call(procedure, group_name, resource_name, place_name)
    except Exception:
        return failed(f"Failed to release resource {exporter}/{place_name}/{resource_name}.")


@labby_serialized
async def cli_command(context: Session, command: str) -> Union[str, LabbyError]:
    if command is None or not command:
        return failed("Command must not be empty.")
    assert (ssh_session := context.ssh_session).client
    context.log.info(
        f"Issuing labgrid-client command: labgrid-client {command}")
    try:
        (_, sout, serr) = ssh_session.client.exec_command(
            command=f"export LG_USERNAME={context.user_name}; labgrid-client {command}")
        so = str(sout.read(), encoding='utf-8')
        if se := str(serr.read(), encoding='utf-8'):
            so += f"\n\n{se}"
        return so
    except Exception:
        return failed("Failed to execute cli command.")


@labby_serialized
async def username(context: Session) -> Union[str, LabbyError]:
    return context.user_name or failed("Username has not been set correctly.")
