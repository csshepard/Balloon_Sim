import os
from astral import Location
from collections import namedtuple
from flask import Flask, render_template, redirect
from flask_sqlalchemy import SQLAlchemy
import datetime
import requests
import xml.etree.ElementTree as et


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)
app.debug = True


class Simulation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(50))
    site_id = db.Column(db.Integer, db.ForeignKey('launch_site.id'))
    launch_date = db.Column(db.DateTime)
    create_date = db.Column(db.Date)
    kml_file = db.Column(db.Text)
    landing_site = db.relationship('LandingSite',
                                   uselist=False,
                                   backref='simulation')

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
    uuid = db.Column(db.String(50))
    sim_id = db.Column(db.Integer, db.ForeignKey('simulation.id'))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def __init__(self, uuid, latitude, longitude, sim_id):
        self.uuid = uuid
        self.latitude = latitude
        self.longitude = longitude
        self.sim_id = sim_id


Locale = namedtuple('Locale',
                    'name, region, latitude, longitude, tz_name, elevation')

raylen = Locale('RayLen', 'US',
                35.970950, -80.505930,
                'America/New_York', 238)
pilot_mountain = Locale('Pilot Mtn', 'US',
                        36.340489, -80.480438,
                        'America/New_York', 673)
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
    r = requests.post(url='http://predict.habhub.org/'
                          'ajax.php?action=submitForm', data=payload)
    return r.json()


def get_kml(uuid):
    r = requests.get('http://predict.habhub.org/kml.php',
                     params={'uuid': uuid})
    if r.status_code == 200:
        return r.text
    return get_kml(uuid)


def get_landing_site(kml):
    ns = {'kml': "http://www.opengis.net/kml/2.2"}
    root = et.fromstring(kml)
    document = root.find('kml:Document', ns)
    for place in document.findall('kml:Placemark', ns):
        if place.find('kml:name', ns).text == 'Predicted Balloon Landing':
            land_coord = place.find('kml:Point', ns).\
                find('kml:coordinates', ns).text
            return land_coord


def run_simulation(date):
    for site in LOCATIONS:
        site_row = LaunchSite.query.filter_by(name=site.name).one()
        if type(date) == str:
            date = datetime.datetime.strptime(date, '%d-%m-%Y')
        launch_datetime = get_sunrise(site, date)
        uuid_data = get_uuid(site, launch_datetime,
                             ASCENT_RATE, BURST_ALTITUDE, DRAG)
        if uuid_data['valid'] == 'true':
            if Simulation.query.filter_by(uuid=uuid_data['uuid']).\
                    filter_by(create_date=datetime.date.today()).first() is None:
                kml = get_kml(uuid_data['uuid'])
                landing_site = get_landing_site(kml)
                landing_coords = landing_site.split(',')
                sim = Simulation(uuid_data['uuid'], site_row.id,
                                 launch_datetime, datetime.date.today(), kml)
                db.session.add(sim)
                l_site = LandingSite(uuid_data['uuid'],
                                     landing_coords[1], landing_coords[0],
                                     sim.id)
                db.session.add(l_site)
                db.session.commit()
        else:
            return uuid_data['error']


@app.route('/')
def home():
    sims = Simulation.query.order_by(Simulation.launch_date)
    return render_template('home.html', sims=sims)


@app.route('/run-sim/<date>')
def run_sim(date):
    r_value = run_simulation(date)
    if r_value is None:
        return redirect('/view-sim/%s' % date)
    else:
        return r_value


@app.route('/view-sim/<date>')
def view_sim(date):
    date_split = date.split('-')
    launch_date = datetime.date(int(date_split[2]), int(date_split[1]),
                                int(date_split[0]))
    sims = Simulation.query.filter(Simulation.launch_date > launch_date).\
        filter(Simulation.launch_date <
               launch_date + datetime.timedelta(days=1))
    return render_template('view-sim.html', sims=sims)


@app.route('/kml/<uuid_date>')
def return_kml(uuid_date):
    uuid, date = uuid_date.split('+')
    date = datetime.datetime.strptime(date, '%Y-%m-%d')
    file = Simulation.query.filter_by(uuid=uuid).\
        filter_by(create_date=date).one().kml_file
    return file


@app.route('/run-sim')
def auto_sim():
    start_date = datetime.date.today()+datetime.timedelta(days=1)
    end_date = start_date + datetime.timedelta(hours=180)
    while start_date < end_date:
        r_value = run_simulation(start_date)
        if r_value is not None:
            return r_value
        start_date += datetime.timedelta(days=1)
    return redirect('/')


@app.route('/landing-sites')
def landing_sites():
    land_points = db.session.query(LandingSite.id, LandingSite.latitude,
                                   LandingSite.longitude, LaunchSite.name).\
        join(Simulation, LandingSite.uuid == Simulation.uuid).\
        join(LaunchSite, Simulation.site_id == LaunchSite.id)
    return render_template('landing-sites.html', landingsites=land_points)



if __name__ == '__main__':
    app.debug = True
    app.run()