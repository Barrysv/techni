from collections import OrderedDict
import binascii
import re
import json
import requests
from bs4 import BeautifulSoup
import toml
import srp
import datetime
import time
import logging
import voluptuous as vol

from homeassistant.const import (
    STATE_UNKNOWN, CONF_NAME, CONF_PASSWORD, CONF_USERNAME,
    CONF_HOST)
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv

DEFAULT_NAME = 'Technicolor Sensor'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the technicolor modem sensor"""
    address = config.get(CONF_HOST)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    name = config.get(CONF_NAME)

    fetch = Fetcher({'address':address, 'username':username, 'password':password})
    fetch.get()
    
    add_devices([TechnicolorModemSensor(hass, fetch, name)], True)
    
class TechnicolorModemSensor(Entity):
    """Representation of a modem Sensor."""

    def __init__(self, hass, fetch, name):
        """Initialize the sensor."""
        self._state = STATE_UNKNOWN
        self._name = name
        self._hass = hass
        self.fetch = fetch
        self._unit_of_measurement = None
        self._attributes = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def available(self):
        """Return if the sensor data is available."""
        return self.fetch.data is not None

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state
    
    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes
        
    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        def fetch_string(soup, title):
            lr = soup.find_all(string=title)
            #D(title)
            #D(lr[0].parent.parent)
            return lr[0].parent.parent.find_next('span').text

        def fetch_pair(soup, title, unit):
            # Find the label
            lr = soup.find_all(string=title)
            # Traverse up to the parent div that also includes the values.
            # Search that div for text with the units (Mbps, dB etc)
            updown = lr[0].parent.parent.find_all(string=re.compile(unit))
            # Extract the float out of eg "4.85 Mbps"
            return (float(t.replace(unit,'').strip()) for t in updown)

        def fetch_line_attenuation(soup, r):
            """ Special case since VDSL has 3 values each for up/down 
                eg "22.5, 64.9, 89.4 dB"
                (measuring attenuation in 3 different frequency bands?)
                we construct {up,down}_attenuation{1,2,3}
            """
            title = "Line Attenuation"
            unit = "dB"
            lr = soup.find_all(string=title)
            updown = lr[0].parent.parent.find_all(string=re.compile(unit))
            for dirn, triple in zip(("up", "down"), updown):
                # [:3] to get rid of N/A from the strange "2.8, 12.8, 18.9,N/A,N/A dB 7.8, 16.7, 24.3 dB"
                vals = (v.strip() for v in triple.replace(unit, '').split(',')[:3])
                for n, t in enumerate(vals, 1):
                    r['%s_attenuation%d' % (dirn, n)] = float(t)

        def fetch_uptime(soup, name):
            """ Returns uptime in seconds """
            uptime = fetch_string(soup, name)
            mat = re.match(r'(?:(\d+)days)? *(?:(\d+)hours)? *(?:(\d+)min)? *(?:(\d+)sec)?', uptime)
            d,h,m,s = (int(x) for x in mat.groups(0))
            return int(datetime.timedelta(days=d, hours=h, minutes=m, seconds=s).total_seconds())

        def parse_broadband(res, html):
            """
            Parses the contents of http://10.1.1.1/modals/broadband-bridge-modal.lp
            to extract link values. 
            The tg-1 doesn't have id attributes so we have to find text labels.
            """
            soup = BeautifulSoup(html, 'html.parser')
            #res['datetime'] = datetime.datetime.now()
            res['up_rate'], res['down_rate'] = fetch_pair(soup, "Line Rate", 'Mbps')
            res['up_maxrate'], res['down_maxrate'] = fetch_pair(soup, "Maximum Line rate", 'Mbps')
            res['up_power'], res['down_power'] = fetch_pair(soup, "Output Power", 'dBm')
            res['up_noisemargin'], res['down_noisemargin'] = fetch_pair(soup, "Noise Margin", 'dB')
            #res['up_transferred'], res['down_transferred'] = fetch_pair(soup, "Data Transferred", "MBytes")
            #fetch_line_attenuation(soup, res)
            res['dsl_uptime_seconds'] = fetch_uptime(soup ,'DSL Uptime')
            res['dsl_uptime'] = fetch_string(soup ,'DSL Uptime')
            #res['dsl_mode'] = fetch_string(soup, 'DSL Mode')
            #res['dsl_type'] = fetch_string(soup, 'DSL Type')
            res['dsl_status'] = fetch_string(soup, 'DSL Status')
            # integer kbps are easier to work with in scripts
            #for n in 'down_rate', 'up_rate', 'down_maxrate', 'up_maxrate':
            #    res[n] = int(res[n] * 1000)
            return res

        def parse_gateway(res, html):
            """ Parses the contents of http://10.1.1.1/modals/gateway-modal.lp """
            soup = BeautifulSoup(html, 'html.parser')
            names = [
                'Product Vendor',
                'Product Name',
                'Software Version',
                'Firmware Version',
                'Hardware Version',
                'Serial Number',
                'MAC Address',
            ]
            for n in names:
                res[n.lower().replace(' ', '_')] = fetch_string(soup, n)
            res['uptime'] = fetch_uptime(soup, 'Uptime')
         
        self.fetch.get()
        #stats_page, gateway_page = self.fetch.data
        stats_page = self.fetch.data
        stats = OrderedDict()
        if stats_page:
            parse_broadband(stats, stats_page)
        #if gateway_page:
        #    parse_gateway(stats, gateway_page)
        self._attributes = dict(stats)
        self._state = stats['dsl_status']

class Fetcher(object):
    """Class for handling the data retrieval."""
    def __init__(self, config):
        self.config = config
        self.top_url = 'http://%s' % self.config['address']
        self.session = None
        self.data = None

    def connect(self):
        """ Authenticates with the modem. 
        Returns a session on success or throws an exception 
        """
        session = requests.Session()

        ### Fetch CSRF
        csrf_url = '%s/login.lp?action=getcsrf' % self.top_url
        csrf = session.get(csrf_url).text
        if len(csrf) != 64:
            #D("csrf %s", csrf)
            raise Exception("Bad csrf response")
        #D("csrf: %s" % csrf)

        ### Perform SRP
        srp_user = srp.User(self.config['username'], self.config['password'],
            hash_alg=srp.SHA256, ng_type=srp.NG_2048)
        # Bit of a bodge. Seems the router uses a custom k value? Thanks to nbntest
        if hasattr(srp._mod, 'BN_hex2bn'):
            # _mod == _ctsrp, openssl
            srp._mod.BN_hex2bn(srp_user.k, b'05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300')
        else:
            # _mod == _pysrp, pure python
            srp_user.k = int('05b9e8ef059c6b32ea59fc1d322d37f04aa30bae5aa9003b8321e21ddb04e300', 16)

        I, A = srp_user.start_authentication()
        A = binascii.hexlify(A)
        #D("A: %d %s" % (len(A), A))

        auth_url = '%s/authenticate' % self.top_url
        req_data = {
            'I': I, 
            'A': A, 
            'CSRFtoken': csrf
        }
        ### Send the first SRP request
        auth1 = session.post(auth_url, data=req_data)
        if auth1.status_code != 200:
            #D(auth1.text)
            raise Exception("Error authenticating %d" % auth1.status_code)
        j = auth1.json()
        s, B = j['s'], j['B']
        #D("s: %d %s" % (len(s), s))
        #D("B: %d %s" % (len(B), B))
        s = binascii.unhexlify(s)
        B = binascii.unhexlify(B)

        M = srp_user.process_challenge(s, B)
        M = binascii.hexlify(M)
        #D("M: %d %s" % (len(M), M))
        req_data = {
            'M': M, 
            'CSRFtoken': csrf
        }
        ### Send our reponse to the SRP challenge
        auth2 = session.post(auth_url, data=req_data)

        if auth2.status_code != 200:
            #D(auth2.text)
            raise Exception("Didn't connect, error %d" % auth2.status_code)

        j = auth2.json()
        if 'error' in j:
            #D(j)
            raise Exception("Authentication error. Wrong password? (%s)" % j['error'])

        return session

    def get(self):
        if not self.session:
            self.session = self.connect()

        modem_url = '%s/modals/broadband-bridge-modal.lp' % self.top_url
        r = self.session.get(modem_url)

        #gateway_url = '%s/modals/gateway-modal.lp' % self.top_url
        #g = self.session.get(gateway_url)

        #self.data = r.text, g.text
        self.data = r.text
		
		
# Special thanks to Matt Johnston
# Portions of the code borrowed from https://github.com/mkj/tgiistat
# Copyright (c) 2018 Matt Johnston
# All rights reserved.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
