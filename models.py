from app import db
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import HSTORE


class Simulation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(50))
    site_id = db.Column(db.Integer, db.ForeignKey('launch_site.id'))
    launch_date = db.Column(db.DateTime)
    create_date = db.Column(db.Date)
    create_datetime = db.Column(db.DateTime)
    kml_file = db.Column(db.Text)
    landing_site = db.relationship('LandingSite',
                                   uselist=False,
                                   backref='simulation')

    def __init__(self, uuid, site_id, launch_date,
                 create_date, create_datetime, kml_file):
        self.uuid = uuid
        self.site_id = site_id
        self.launch_date = launch_date
        self.create_date = create_date
        self.kml_file = kml_file
        self.create_datetime = create_datetime


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


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(MutableDict.as_mutable(HSTORE))


class Coordinate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    altitude = db.Column(db.Float)
    timestamp = db.Column(db.DateTime)
    noteworthy = db.Column(db.String(25))

    def __init__(self, latitude, longitude, altitude, timestamp):
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.timestamp = timestamp

    @property
    def serialize(self):
        return {
            'id': self.id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'timestamp': self.timestamp.strftime('%H:%M:%S'),
            'noteworthy': self.noteworthy
        }

