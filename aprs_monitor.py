import datetime
import aprslib
import smtplib
import os
from sqlalchemy import desc
from app import db, Coordinate
import logging

logging.basicConfig(level=logging.DEBUG)


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
    callsign = 'BH1NIN-9'
    ais = aprslib.IS(callsign=callsign, host='noam.aprs2.net', port=14580)
    ais.set_filter('p/%s' % callsign)
    ais.connect()

    def callback(packet):
        print('------------\nPacket Recieved\n------------')
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
                db.session.add(new_coord)
                print('------------\nNew Coordinates\n------------')
                if (len(latest_2) > 1 and
                        latest_2[0].altitude >= latest_2[1] .altitude and
                        new_coord.altitude != 0 and
                        new_coord.altitude < latest_2[0].altitude):
                    balloon_popped(latest_2[0])
                db.session.commit()
    ais.consumer(callback)


if __name__ == "__main__":
    try:
        get_coords()
    except KeyboardInterrupt:
        print('Quiting APRS Monitor')
