import datetime
import aprslib
import smtplib
import os
from twitter import *
from sqlalchemy import desc
from app import db, Coordinate
import logging

logging.basicConfig(level=logging.DEBUG)
twit = Twitter(auth=OAuth(os.environ['TWITTER_TOKEN'],
                          os.environ['TWITTER_TOKEN_SECRET'],
                          os.environ['TWITTER_CONSUMER'],
                          os.environ['TWITTER_CONSUMER_SECRET']))
twitter_message = "Payload Location: Latitude: {lat:.5} Longitude: {lng:.5} " \
                  "Altitude: {alt:.5} http://bit.ly/1IvyO0E #GSBChallenge #NSC01"


def balloon_launched():
    twit.statuses.update(status='  '.join(["up, up, and away.",
                                          "The payload is on it's way to near space.",
                                          "http://bit.ly/1IvyO0E",
                                          ]))


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


def callback(packet):
    logging.log(logging.DEBUG,
                '------------\nPacket Received\n------------')
    if packet.get('latitude') and packet.get('longitude'):
        new_coord = Coordinate(timestamp=datetime.datetime.utcnow(),
                               latitude=packet['latitude'],
                               longitude=packet['longitude'],
                               altitude=packet.get('altitude', 0))
        latest_2 = db.session.query(Coordinate).\
            order_by(desc(Coordinate.timestamp)).limit(2).all()
        if (len(latest_2) == 0 and new_coord.altitude > 250) or \
                (new_coord.latitude != latest_2[0].latitude and
                 new_coord.longitude != latest_2[0].longitude and
                 new_coord.timestamp > latest_2[0].timestamp):
            db.session.add(new_coord)
            logging.log(logging.DEBUG,
                        '------------\nNew Coordinate\n------------')
            if len(latest_2) == 0:
                balloon_launched()
            elif (len(latest_2) > 1 and
                    latest_2[0].altitude >= latest_2[1] .altitude and
                    new_coord.altitude != 0 and
                    new_coord.altitude < latest_2[0].altitude):
                balloon_popped(latest_2[0])
            twit.statuses.update(status=twitter_message.
                                 format(lat=new_coord.latitude,
                                        lng=new_coord.longitude,
                                        alt=new_coord.altitude))
            db.session.commit()


def get_coords():
    callsign = 'OH8GZZ-9'
    ais = aprslib.IS(callsign=callsign, host='noam.aprs2.net', port=14580)
    ais.set_filter('p/%s' % callsign)
    ais.connect()
    ais.consumer(callback)


if __name__ == "__main__":
    try:
        get_coords()
    except KeyboardInterrupt:
        logging.log(logging.DEBUG, 'Quiting APRS Monitor')
