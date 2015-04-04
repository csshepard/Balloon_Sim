import os
from astral import Location
from collections import namedtuple
from flask import Flask, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
import datetime
import requests
import xml.etree.ElementTree as ET
import re


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)
app.debug = True


class Simulation(db.Model):
    uuid = db.Column(db.String(50), primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('launch_site.id'))
    launch_date = db.Column(db.DateTime)
    create_date = db.Column(db.Date)
    kml_file = db.Column(db.Text)
    landing_site = db.relationship('LandingSite', uselist=False, backref='simulation')

    def __init__(self, uuid, site_id, launch_date, create_date, kml_file):
        self.uuid = uuid
        self.site_id = site_id
        self.launch_date = launch_date
        self.create_date = create_date
        self.kml_file = kml_file


class LaunchSite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    elevation = db.Column(db.Integer)
    simulations = db.relationship('Simulation', backref='launch_site')

    def __init__(self, name, latitude, longitude, elevation):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation


class LandingSite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(50), db.ForeignKey('simulation.uuid'))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def __init__(self, uuid, latitude, longitude):
        self.uuid = uuid
        self.latitude = latitude
        self.longitude = longitude


Locale = namedtuple('Locale', 'name, region, latitude, longitude, tz_name, elevation')

raylen = Locale('RayLen', 'US', 35.970950, -80.505930, 'America/New_York', 238)
pilot_mountain = Locale('Pilot Mtn', 'US', 36.340489, -80.480438, 'America/New_York', 673)
LOCATIONS = [raylen, pilot_mountain]
ASCENT_RATE = 2.92
BURST_ALTITUDE = 33000
DRAG = 4.572

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
               'submit': 'Run+Prediction'}
    r = requests.post(url='http://predict.habhub.org/ajax.php?action=submitForm', data=payload)
    return r.json()


def get_kml(uuid):
    r = requests.get('http://predict.habhub.org/kml.php', params={'uuid': uuid})
    return r.text


def get_landing_site(kml):
    ns = {'kml': "http://www.opengis.net/kml/2.2"}
    root = ET.fromstring(kml)
    document = root.find('kml:Document', ns)
    for place in document.findall('kml:Placemark', ns):
        if place.find('kml:name', ns).text == 'Predicted Balloon Landing':
            #time_date = re.compile('(\d{2}:\d{2}).((\d{2}/){2}\d{4})')
            #land_text = place.find('kml:description', ns).text
            #land_time = time_date.search(land_text)
            #land_time = land_time.string[land_time.start():land_time.end()]
            #dtformat = '%H:%M %d/%m/%Y'
            #landing_time = datetime.datetime.strptime(land_time, dtformat)
            land_coord = place.find('kml:Point', ns).find('kml:coordinates', ns).text
            return land_coord #, landing_time


@app.route('/')
def home():
    return 'Hello World'


@app.route('/run-sim/<date>')
def run_sim(date):
    for site in LOCATIONS:
        site_row = LaunchSite.query.filter_by(name=site.name).one()
        launch_datetime = get_sunrise(site, datetime.datetime.strptime(date, '%d-%m-%Y'))
        uuid_data = get_uuid(site, launch_datetime, ASCENT_RATE, BURST_ALTITUDE, DRAG)
        if uuid_data['valid'] == 'true':
            kml = get_kml(uuid_data['uuid'])
            landing_site = get_landing_site(kml)
            landing_coords = landing_site.split(',')
            sim = Simulation(uuid_data['uuid'], site_row.id, launch_datetime,
                             datetime.date.today(), kml)
            if Simulation.query.filter_by(uuid=uuid_data['uuid']).count() == 0:
                db.session.add(sim)
                l_site = LandingSite(uuid_data['uuid'], landing_coords[1], landing_coords[0])
                db.session.add(l_site)
                db.session.commit()
            return redirect('/view-sim/%s' % date)
        else:
            return uuid_data['error']


@app.route('/view-sim/<date>')
def view_sim(date):
    date_split = date.split('-')
    launch_date = datetime.date(int(date_split[2]), int(date_split[1]), int(date_split[0]))
    sims = Simulation.query.filter(Simulation.launch_date > launch_date).filter(Simulation.launch_date < launch_date + datetime.timedelta(days=1))
    return render_template('view_sim.html', sims=sims)


@app.route('/kml/<uuid>')
def return_kml(uuid):
    file = Simulation.query.filter_by(uuid=uuid).one().kml_file
    return file


if __name__ == '__main__':
    app.debug = True
    app.run()