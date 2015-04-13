import datetime
import aprslib
import smtplib
import os
from sqlalchemy import desc
from app import db, Coordinate


def balloon_popped(coordinate):
    timeformat = '%I:%M:%S'
    msg = '\r\n'.join([
        'From: csshepard@gmail.com',
        'To: csshepard@gmail.com',
        'Subject: Balloon Popped',
        '',
        'The balloon popped at {time}\nIt was located at longitude {long}, latitude {lat}, altitude {alt}'.
        format(time=coordinate.timestamp.strftime(timeformat),
               lat=coordinate.latitude,
               long=coordinate.longitude,
               alt=coordinate.altitude)])
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


def get_coords():
    callsign = 'NC4CAP-1'
    ais = aprslib.IS(callsign, 'lga.aprs2.net', 14580)
    ais.set_filter('p/%s' % callsign)
    ais.connect()

    def callback(packet):
        if packet.get('latitude') and packet.get('longitude'):
            new_coord = Coordinate(timestamp=datetime.datetime.utcnow(),
                                   latitude=packet.latitude,
                                   longitude=packet.longitude,
                                   altitude=packet.get('altitude', 0))
            latest = db.session.query(Coordinate).\
                order_by(desc(Coordinate.timestamp)).latest()
            if latest in None or (new_coord.latitude != latest.latitude and
                                  new_coord.longitude != latest.longitude and
                                  new_coord.timestamp > latest.timestamp):
                db.session.add(new_coord)
                if (latest is not None and new_coord.altitude != 0 and
                        new_coord.altitude < latest.altitude):
                    balloon_popped(latest)
                db.session.commit()
    ais.consumer(callback)