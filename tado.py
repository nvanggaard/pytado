import asyncio
import aiohttp
import async_timeout
import time

URL_BASE = 'https://my.tado.com'
URL_TOKEN = '/oauth/token'
URL_ME = '/api/v2/me'
URL_ZONES = lambda home_id: "/api/v2/homes/{}/zones".format(home_id)
URL_STATE = lambda home_id, zone: "/api/v2/homes/{}/zones/{}/state".format(home_id, zone)

class TadoAccessToken:
    def __init__(self, token, refresh_token, expires):
        self.token = token
        self.refresh_token = refresh_token
        self.expires = expires
        self.create_time = time.time()

    def is_expired(self):
        return (self.create_time + self.expires) < time.time()

class TadoHome:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class TadoZone:
    def __init__(self, id, name, home_id):
        self.id = id
        self.name = name
        self.home_id = home_id

class TadoClient:
    def __init__(self, loop):
        self.session = aiohttp.ClientSession(loop=loop)

    def __del__(self):
        self.session.close()

    def get_headers(self, credentials):
        return {"Authorization" : "Bearer {}".format(credentials.token)}

    async def get_token(self, username, password):
        url = URL_BASE + URL_TOKEN
        data = { 'client_id'  : 'tado-webapp',
                 'grant_type' : 'password',
                 'scope'      : 'home.user',
                 'username'   : username,
                 'password'   : password }

        with async_timeout.timeout(10):
            async with self.session.post(url, data=data) as response:
                response_data = await response.json()
                return TadoAccessToken(response_data['access_token'],
                                   response_data['refresh_token'],
                                   response_data['expires_in'])

    async def refresh_token(self, credentials: TadoAccessToken):
        url = URL_BASE + URL_TOKEN
        data = { 'client_id'     : 'tado-webapp',
                 'grant_type'    : 'refresh_token',
                 'scope'         : 'home.user',
                 'refresh_token' : credentials.refresh_token }
        with async_timeout.timeout(10):
            async with self.session.post(url, data=data) as response:
                response_data = await response.json()
                return TadoAccessToken(response_data['access_token'],
                                   response_data['refresh_token'],
                                   response_data['expires_in'])


    async def get_state(self, credentials: TadoAccessToken, zone):
        url = URL_BASE + URL_STATE(zone.home_id, zone.id)
        with async_timeout.timeout(10):
            async with self.session.get(url, headers=self.get_headers(credentials)) as response:
                response_data = await response.json()
                return response_data

    async def get_homes(self, credentials: TadoAccessToken):
        url = URL_BASE + URL_ME
        with async_timeout.timeout(10):
            async with self.session.get(url, headers=self.get_headers(credentials)) as response:
                response_data = await response.json()
                return list(map(lambda home: TadoHome(home['id'], home['name']), response_data['homes']))

    async def get_zones(self, credentials: TadoAccessToken, home):
        url = URL_BASE + URL_ZONES(home.id)
        with async_timeout.timeout(10):
            async with self.session.get(url, headers=self.get_headers(credentials)) as response:
                response_data = await response.json()
                return list(map(lambda zone: TadoZone(zone['id'], zone['name'], home.id), response_data))

class TadoService:
    def __init__(self, client, username, password):
        self.username = username
        self.password = password
        self.client = client
        self.credentials = None

    async def get_zone_data_by_index(self, home, zone):
        await self.ensure_credentials()
        homes = await self.get_homes()
        zones = await self.get_zones(homes[home])
        return await self.client.get_state(self.credentials, zones[zone])

    async def get_all_zones_data(self):
        data = {}
        await self.ensure_credentials()
        homes = await self.get_homes()
        for home in homes:
            data[home.id] = {}
            zones = await self.get_zones(home)
            for zone in zones:
                data[home.id][zone.id] = await self.client.get_state(self.credentials, zone)

        return data

    async def get_zone_data(self, zone):
        await self.ensure_credentials()
        return await self.client.get_state(self.credentials, zone)

    async def get_homes(self):
        await self.ensure_credentials()
        return await self.client.get_homes(self.credentials)

    async def get_zones(self, home):
        await self.ensure_credentials()
        return await self.client.get_zones(self.credentials, home)

    async def ensure_credentials(self):
        if self.credentials == None:
            self.credentials = await self.client.get_token(self.username, self.password)
        if self.credentials.is_expired():
            self.credentials = await self.client.refresh_token(self.credentials)
