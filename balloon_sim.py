from astral import Location
from collections import namedtuple
from flask import Flask
import datetime
import requests
import xml.etree.ElementTree as ET
import re
import psycopg2


app = Flask(__name__)
app.config['SQALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URI']
db = SQLAlchemy(app)

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
                time_date = re.compile('(\d{2}:\d{2}).((\d{2}/){2}\d{4})')
                land_text = place.find('kml:description', ns).text
                land_time = time_date.search(land_text)
                land_time = land_time.string[land_time.start():land_time.end()]
                dtformat = '%H:%M %d/%m/%Y'
                landing_time = datetime.datetime.strptime(land_time, dtformat)
                land_coord = place.find('kml:Point', ns).find('kml:coordinates', ns).text
                return land_coord, landing_time
    except AttributeError:
        pass


@app.route('/')


if __name__ == '__main__':
    app.debug = True
    app.run()