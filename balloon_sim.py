from astral import Location
from collections import namedtuple
import datetime
import requests


Locale = namedtuple('Locale', 'name, region, latitude, longitude, tz_name, elevation')


def get_sunrise(place, date):
    return Location(place).sunrise(date=date, local=False)


def get_uuid(place, launchdate, ascent_rate, burst_altitude, descent_speed):
    payload = {'launchsite': 'Other',
               'lat': place.latitude,
               'lon': place.longitude,
               'initial_alt': place.elevation,
               'hour': launchdate.hour,
               'min': launchdate.minute,
               'second': launchdate.second,
               'day': launchdate.day,
               'month': launchdate.month,
               'year': launchdate.year,
               'ascent': ascent_rate,
               'burst': burst_altitude,
               'drag': descent_speed,
               'submit': 'Run Prediction'}
    r = requests.post(url='http://predict.habhub.org/ajax.php?action=submitForm', data= payload)
    data = r.json()
    if data['valid']:
        return data['uuid']


def get_kml(uuid):
    r = requests.get('http://predict.habhub.org/kml.php', params={'uuid': uuid})
    return r.text

