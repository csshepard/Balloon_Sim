import os
from astral import Location
from collections import namedtuple
from flask import Flask, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import cast, desc, func
import datetime
import requests
import xml.etree.ElementTree as et


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)

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
    try:
        root = et.fromstring(kml)
    except et.ParseError:
        return
    document = root.find('kml:Document', ns)
    for place in document.findall('kml:Placemark', ns):
        if place.find('kml:name', ns).text == 'Predicted Balloon Landing':
            land_coord = place.find('kml:Point', ns).\
                find('kml:coordinates', ns).text
            return land_coord


def run_simulation(date):
    sim_count=0
    for site in LOCATIONS:
        site_row = LaunchSite.query.filter_by(name=site.name).one()
        if type(date) == str:
            date = datetime.datetime.strptime(date, '%Y-%m-%d')
        launch_datetime = get_sunrise(site, date)
        uuid_data = get_uuid(site, launch_datetime,
                             ASCENT_RATE, BURST_ALTITUDE, DRAG)
        if uuid_data['valid'] == 'true':
            if Simulation.query.filter_by(uuid=uuid_data['uuid']).\
                    filter_by(create_date=datetime.date.today()).first() is None:
                kml = get_kml(uuid_data['uuid'])
                landing_site = get_landing_site(kml)
                if landing_site is None:
                    continue
                landing_coords = landing_site.split(',')
                sim = Simulation(uuid_data['uuid'], site_row.id,
                                 launch_datetime, datetime.date.today(), kml)
                db.session.add(sim)
                db.session.flush()
                l_site = LandingSite(uuid_data['uuid'],
                                     landing_coords[1], landing_coords[0],
                                     sim.id)
                db.session.add(l_site)
                sim_count += 1
        else:
            return uuid_data['error']
    db.session.commit()
    return sim_count

@app.context_processor
def get_navigation_rows():
    locations = db.session.query(LaunchSite.id, LaunchSite.name).distinct().order_by(LaunchSite.name)
    dt = cast(Simulation.launch_date, db.Date)
    sims = db.session.query(dt).group_by(dt).order_by(desc(dt))
    return dict(nav_locations=locations, nav_sims=sims)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/view-all')
def view_all():
    sims = Simulation.query.order_by(Simulation.launch_date.desc())
    return render_template('view-all.html', sims=sims)


@app.route('/run-sim/<date>')
def run_sim(date):
    r_value = run_simulation(date)
    if r_value is type(str):
        return r_value
    return redirect(url_for('view_sims_by_date', date=date))


@app.route('/view-sim/d/<date>')
def view_sims_by_date(date):
    if type(date) is str:
        date_split = date.split('-')
        date = datetime.date(int(date_split[0]), int(date_split[1]),
                             int(date_split[2]))
    sims = Simulation.query.filter(Simulation.launch_date > date).\
        filter(Simulation.launch_date <
               date + datetime.timedelta(days=1)).order_by(desc(Simulation.launch_date))
    return render_template('view-sim.html', sims=sims)


@app.route('/view-sim/l/<site_id>')
def view_sims_by_launch(site_id):
    sims = Simulation.query.filter_by(site_id=site_id).order_by(desc(Simulation.launch_date))
    return render_template('view-sim.html', sims=sims)


@app.route('/kml/<id>')
def return_kml(id):
    file = Simulation.query.filter_by(id=id).first_or_404().kml_file
    return file


@app.route('/run-sim')
def auto_sim():
    start_date = datetime.date.today()+datetime.timedelta(days=1)
    end_date = datetime.datetime.now() + datetime.timedelta(hours=170)
    sim_count = 0
    while datetime.datetime.combine(start_date, datetime.time()) < end_date:
        r_value = run_simulation(start_date)
        if r_value is type(str):
            return r_value
        sim_count += r_value
        start_date += datetime.timedelta(days=1)
    return '%s new simulations added' % sim_count


@app.route('/landing-sites')
def landing_sites():
    land_points = db.session.query(LandingSite.id, LandingSite.latitude,
                                   LandingSite.longitude, LaunchSite.name,
                                   Simulation.launch_date,
                                   Simulation.site_id).\
        join(Simulation, LandingSite.sim_id == Simulation.id).\
        join(LaunchSite, Simulation.site_id == LaunchSite.id)
    lp_sub = land_points.subquery()
    avgs = db.session.query(lp_sub.c.site_id.label('id'),
                            func.avg(lp_sub.c.latitude).label('lat'),
                           func.avg(lp_sub.c.longitude).label('long')).\
        group_by(lp_sub.c.site_id)

    return render_template('landing-sites.html',
                           avgs=avgs, landingsites=land_points)


if __name__ == '__main__':
    app.debug = True
    app.run()
