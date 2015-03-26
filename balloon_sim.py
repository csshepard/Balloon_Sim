from astral import Location
from collections import namedtuple
import datetime
import requests
import xml.etree.ElementTree as ET

Locale = namedtuple('Locale', 'name, region, latitude, longitude, tz_name, elevation')


def get_sunrise(place, date):
    return Location(place).sunrise(date=date, local=False)


def get_uuid(place, launch_date, ascent_rate, burst_altitude, descent_speed):
    payload = {'launchsite': 'Other',
               'lat': place.latitude,
               'lon': place.longitude,
               'initial_alt': place.elevation,
               'hour': launch_date.hour,
               'min': launch_date.minute,
               'second': launch_date.second,
               'day': launch_date.day,
               'month': launch_date.month,
               'year': launch_date.year,
               'ascent': ascent_rate,
               'burst': burst_altitude,
               'drag': descent_speed,
               'submit': 'Run Prediction'}
    r = requests.post(url='http://predict.habhub.org/ajax.php?action=submitForm', data=payload)
    data = r.json()
    if data['valid']:
        return data['uuid']


def get_kml(uuid):
    r = requests.get('http://predict.habhub.org/kml.php', params={'uuid': uuid})
    return r.text


def get_landing_site(kml):
    ns = {'kml': "http://www.opengis.net/kml/2.2"}
    root = ET.fromstring(kml)
    try:
        document = root.find('kml:Document', ns)
        for place in document.findall('kml:Placemark', ns):
            if place.find('kml:Name', ns).text == 'Predicted Balloon Landing':
                return place.find('kml:Point', ns).find('kml:coordinates', ns).text
    except AttributeError:
        pass



