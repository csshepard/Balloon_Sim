import os
from astral import Location
from collections import namedtuple
from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import cast, desc, func
from celery import Celery
import aprslib
import datetime
import requests
import xml.etree.ElementTree as et
import smtplib
from twitter import *


app = Flask(__name__)
app.config.from_object(os.environ['APP_SETTINGS'])
db = SQLAlchemy(app)

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

from models import *


Locale = namedtuple('Locale',
                    'name, region, latitude, longitude, tz_name, elevation')

raylen = Locale('RayLen', 'US',
                35.970950, -80.505930,
                'America/New_York', 238)
pilot_mountain = Locale('Pilot Mtn', 'US',
                        36.340489, -80.480438,
                        'America/New_York', 673)
LOCATIONS = [raylen, pilot_mountain]

twit = Twitter(auth=OAuth(os.environ['TWITTER_TOKEN'],
                          os.environ['TWITTER_TOKEN_SECRET'],
                          os.environ['TWITTER_CONSUMER'],
                          os.environ['TWITTER_CONSUMER_SECRET']))
twitter_message = "Payload Location: Latitude: {lat:.5} Longitude: {lng:.5} " \
                  "Altitude: {alt:.5} http://bit.ly/1IvyO0E #GSBChallenge #NSC01"


def balloon_launched(coordinate):
    twit.statuses.update(status='  '.join(["up, up, and away.",
                                          "The payload is on it's way to near space.",
                                          "http://bit.ly/1IvyO0E",
                                          ]))
    coordinate.noteworthy = "Balloon Launched"
    return coordinate


def balloon_popped(coordinate):
    twit.statuses.update(status='  '.join(["Here it comes.",
                                           "The balloon popped."]))
    time_format = '%I:%M:%S'
    msg = '\r\n'.join([
        'From: csshepard@gmail.com',
        'To: csshepard@gmail.com',
        'Subject: Balloon Popped',
        '',
        'The balloon popped at {time}\n'
        'It was located at longitude {long}, latitude {lat}, altitude {alt}'.
        format(time=coordinate.timestamp.strftime(time_format),
               lat=coordinate.latitude,
               long=coordinate.longitude,
               alt=float(coordinate.altitude))])
    fromaddr = 'csshepard@gmail.com'
    toaddr = 'csshepard@gmail.com'
    username = 'csshepard@gmail.com'
    password = os.environ['GPSWD']
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(username, password)
    server.sendmail(fromaddr, toaddr, msg)
    server.quit()
    coordinate.noteworthy = "Balloon Popped"
    return coordinate


def callback(packet):
    if packet.get('latitude') and packet.get('longitude'):
        new_coord = Coordinate(timestamp=datetime.datetime.utcnow(),
                               latitude=packet['latitude'],
                               longitude=packet['longitude'],
                               altitude=packet.get('altitude', 0))
        latest_2 = db.session.query(Coordinate).\
            order_by(desc(Coordinate.timestamp)).limit(2).all()
        if len(latest_2) == 0 or \
                (new_coord.latitude != latest_2[0].latitude and
                 new_coord.longitude != latest_2[0].longitude and
                 new_coord.timestamp > latest_2[0].timestamp):
            if len(latest_2) == 0:
                new_coord = balloon_launched(new_coord)
            elif (len(latest_2) > 1 and
                    latest_2[0].altitude >= latest_2[1] .altitude and
                    new_coord.altitude != 0 and
                    new_coord.altitude < latest_2[0].altitude):
                latest_2[0] = balloon_popped(latest_2[0])
                db.session.add(latest_2[0])
            twit.statuses.update(status=twitter_message.
                                 format(lat=new_coord.latitude,
                                        lng=new_coord.longitude,
                                        alt=float(new_coord.altitude)))
            db.session.add(new_coord)
            db.session.commit()


def get_position(callsign):
    ais = aprslib.IS(callsign=callsign, host='noam.aprs2.net', port=14580)
    ais.set_filter('p/%s' % callsign)
    ais.connect()
    ais.consumer(callback=callback, immortal=True)


@celery.task(bind=True)
def aprs_listen(self):
    try:
        global_var = db.session.query(Settings).one()
        callsign = global_var.data.get('CALLSIGN', 'N4CAP-11')
        msg = '\r\n'.join([
            'From: csshepard@gmail.com',
            'To: csshepard@gmail.com',
            'Subject: listening to aprs',
            '',
            'listening to aprs'])
        fromaddr = 'csshepard@gmail.com'
        toaddr = 'csshepard@gmail.com'
        username = 'csshepard@gmail.com'
        password = os.environ['GPSWD']
        server = smtplib.SMTP('smtp.gmail.com:587')
        server.ehlo()
        server.starttls()
        server.login(username, password)
        server.sendmail(fromaddr, toaddr, msg)
        server.quit()
        get_position(callsign)
    except (TwitterHTTPError, smtplib.SMTPException) as exc:
        self.retry(exc=exc)


aprs_listen.delay()


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
    sim_count = 0
    global_var = db.session.query(Settings).one()
    for site in LOCATIONS:
        site_row = LaunchSite.query.filter_by(name=site.name).one()
        if type(date) == str:
            date = datetime.datetime.strptime(date, '%Y-%m-%d')
        launch_datetime = get_sunrise(site, date)
        if ((date.month == 4 and date.day == 21 and
                db.session.query(Simulation.create_datetime).
                filter(Simulation.launch_date == launch_datetime and
                       Simulation.site_id == site_row.id).
                order_by(desc(Simulation.create_datetime)).
                first()[0] + datetime.timedelta(hours=1) <= datetime.datetime.utcnow()) or
                Simulation.query.filter_by(launch_date=launch_datetime).
                filter_by(create_date=datetime.date.today()).
                filter_by(site_id=site_row.id).
                first() is None):
            uuid_data = get_uuid(site, launch_datetime,
                                 global_var.data['ASCENT_RATE'],
                                 global_var.data['BURST_ALTITUDE'],
                                 global_var.data['DRAG_RATE'])
            if uuid_data['valid'] == 'true':
                app.logger.debug('UUID: %s', uuid_data['uuid'])
                kml = get_kml(uuid_data['uuid'])
                landing_site = get_landing_site(kml)
                if landing_site is None:
                    continue
                app.logger.debug('Landing coords string: %s', landing_site)
                landing_coords = landing_site.split(',')
                if landing_coords[0] != '' and landing_coords[1] != '':
                    sim = Simulation(uuid_data['uuid'], site_row.id,
                                     launch_datetime, datetime.date.today(),
                                     datetime.datetime.utcnow(), kml)
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
    locations = db.session.query(LaunchSite.id, LaunchSite.name).distinct().\
        order_by(LaunchSite.name)
    ld = cast(Simulation.launch_date, db.Date)
    sims = db.session.query(ld).group_by(ld).order_by(desc(ld))
    cd_sims = db.session.query(Simulation.create_date).distinct().\
        order_by(desc(Simulation.create_date))
    return dict(nav_locations=locations, nav_sims=sims, cd_sims=cd_sims)


@app.route('/')
def index():
    global_var = db.session.query(Settings).one()
    return render_template('index.html', globals=global_var.data)


@app.route('/view-all')
def view_all():
    sims = Simulation.query.filter(Simulation.launch_date >=
                                   datetime.datetime.utcnow()).\
        order_by(Simulation.launch_date.desc()).\
        order_by(Simulation.site_id)
    return render_template('view-sim.html', sims=sims)


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
               date + datetime.timedelta(days=1)).\
        order_by(desc(Simulation.create_datetime)).\
        order_by(Simulation.site_id)
    return render_template('view-sim.html', sims=sims)


@app.route('/view-sim/c/<date>')
def view_sims_by_create_date(date):
    if type(date) is str:
        date_split = date.split('-')
        date = datetime.date(int(date_split[0]), int(date_split[1]),
                             int(date_split[2]))
    sims = Simulation.query.filter(Simulation.create_date == date).\
        filter(Simulation.launch_date >= datetime.datetime.utcnow()).\
        order_by(desc(Simulation.launch_date)).order_by(Simulation.site_id).\
        order_by(desc(Simulation.create_datetime))
    return render_template('view-sim.html', sims=sims)


@app.route('/view-sim/l/<site_id>')
def view_sims_by_launch(site_id):
    sims = Simulation.query.filter_by(site_id=site_id).\
        filter(Simulation.launch_date >= datetime.datetime.utcnow()).\
        order_by(desc(Simulation.launch_date)).\
        order_by(desc(Simulation.create_datetime))
    return render_template('view-sim.html', sims=sims)


@app.route('/kml/<sim_id>')
def return_kml(sim_id):
    file = Simulation.query.filter_by(id=sim_id).first_or_404().kml_file
    return file


@app.route('/run-sim')
def auto_sim():
    start_date = datetime.datetime.utcnow()+datetime.timedelta(days=1)
    end_date = datetime.datetime.utcnow() + datetime.timedelta(hours=180)
    sim_count = 0
    while start_date < end_date:
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


@app.route('/admin', methods=['GET', 'POST'])
def change_globals():
    global_var = db.session.query(Settings).one()
    if request.method == 'POST':
        if request.form.get('ASCENT_RATE'):
            global_var.data['ASCENT_RATE'] = request.form['ASCENT_RATE']
        if request.form.get('BURST_ALTITUDE'):
            global_var.data['BURST_ALTITUDE'] = request.form['BURST_ALTITUDE']
        if request.form.get('DRAG_RATE'):
            global_var.data['DRAG_RATE'] = request.form['DRAG_RATE']
        if request.form.get('CALLSIGN'):
            global_var.data['CALLSIGN'] = request.form['CALLSIGN']
        db.session.add(global_var)
        db.session.commit()
    return render_template('admin.html', globals=global_var.data)


@app.route('/api/get_coords')
def get_coords():
    get_all = request.args.get('all', False) == 'True'
    coords = Coordinate.query.order_by(Coordinate.timestamp)
    if coords.first() is not None:
        if get_all:
            coords = coords.all()
        else:
            coords = [coords.all()[-1]]
        if coords[0] is not None:
            return jsonify(coordinates=[i.serialize for i in coords])
    return jsonify()


@app.route('/launch_day')
def launch_day():
    return render_template('launch_day.html')


if __name__ == '__main__':
    app.run()
