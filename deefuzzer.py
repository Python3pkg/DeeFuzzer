#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright Guillaume Pellerin (2006-2009)

# <yomguy@parisson.com>

# This software is a computer program whose purpose is to stream audio
# and video data through icecast2 servers.

# This software is governed by the CeCILL  license under French law and
# abiding by the rules of distribution of free software.  You can  use, 
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info". 

# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability. 

# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or 
# data to be ensured and,  more generally, to use and operate it in the 
# same conditions as regards security.

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

# Author: Guillaume Pellerin <yomguy@parisson.com>

import os
import sys
import time
import datetime
import string
import random
import Queue
import shout
import subprocess
import platform
from threading import Thread
from tools import *

version = '0.3.1'
year = datetime.datetime.now().strftime("%Y")
platform_system = platform.system()


def prog_info():
    desc = """ deefuzzer : easy and instant media streaming tool
 version : %s
 running on system : %s

 Copyright (c) 2007-%s Guillaume Pellerin <yomguy@parisson.com>
 All rights reserved.

 This software is licensed as described in the file COPYING, which
 you should have received as part of this distribution. The terms
 are also available at http://svn.parisson.org/deefuzzer/DeeFuzzerLicense

 depends : python, python-xml, python-shout, libshout3, icecast2
 recommends : python-mutagen
 provides : python-shout

 Usage : deefuzzer $1
  where $1 is the path for a XML config file
  ex: deefuzzer example/myfuzz.xml
 
 see http://svn.parisson.org/deefuzzer/ for more details
        """

    return desc % (version, platform_system, year)


class DeeFuzzerError:
    """The DeeFuzzer main error class"""
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return 'DeeFuzzer Error : ' + self.message


class DeeFuzzerStreamError:
    """The DeeFuzzer stream error class"""
    def __init__(self, message, command, subprocess):
        self.message = message
        self.command = str(command)
        self.subprocess = subprocess

    def __str__(self):
        if self.subprocess.stderr != None:
            error = self.subprocess.stderr.read()
        else:
            error = ''
        return "%s ; command: %s; error: %s" % (self.message,
                                                self.command,
                                                error)


class DeeFuzzer(Thread):
    """a DeeFuzzer diffuser"""

    def __init__(self, conf_file):
        Thread.__init__(self)
        self.conf_file = conf_file
        self.conf = self.get_conf_dict()
        if 'log' in self.conf['deefuzzer'].keys():
            self.logger = Logger(self.conf['deefuzzer']['log'])
        else:
            self.logger = Logger('.' + os.sep + 'deefuzzer.log')
        if 'm3u' in self.conf['deefuzzer'].keys():
            self.m3u = self.conf['deefuzzer']['m3u']
        else:
            self.m3u = '.' + os.sep + 'deefuzzer.m3u'

    def get_conf_dict(self):
        confile = open(self.conf_file,'r')
        conf_xml = confile.read()
        confile.close()
        return xmltodict(conf_xml,'utf-8')

    def set_m3u_playlist(self):
        m3u_dir = os.sep.join(self.m3u.split(os.sep)[:-1])
        if not os.path.exists(m3u_dir):
            os.makedirs(m3u_dir)
        m3u = open(self.m3u, 'w')
        i = 1
        m3u.write('#EXTM3U\n')
        for s in self.stations:
            info = '#EXTINF:%s,%s' % (str(i), s.channel.name + ' (' + s.short_name + ')\n')
            url =  s.channel.protocol + '://' + s.channel.host + ':' + str(s.channel.port) + s.channel.mount + '\n'
            m3u.write(info)
            m3u.write(url)
            i += 1
        m3u.close()

    def run(self):
        if isinstance(self.conf['deefuzzer']['station'], dict):
            # Fix wrong type data from xmltodict when one station (*)
            nb_stations = 1
        else:
            nb_stations = len(self.conf['deefuzzer']['station'])

        # Create a Queue
        # Not too much, otherwise, you will get memory leaks !
        q = Queue.Queue(1)

        # Create a Producer 
        p = Producer(q)
        p.start()

        # Set the deefuzzer logger
        self.logger.write('Starting DeeFuzzer v' + version)
        self.logger.write('Using libshout version %s' % shout.version())

        # Define the buffer_size
        self.buffer_size = 65536
        self.logger.write('Buffer size per station = ' + str(self.buffer_size))

        # Init all Stations
        self.stations = []
        self.logger.write('Number of stations : ' + str(nb_stations))
        for i in range(0,nb_stations):
            if isinstance(self.conf['deefuzzer']['station'], dict):
                station = self.conf['deefuzzer']['station']
            else:
                station = self.conf['deefuzzer']['station'][i]
            # Create a Station
            self.stations.append(Station(station, q, self.buffer_size, self.logger))

        # Create M3U playlist
        self.logger.write('Writing M3U file to : ' + self.m3u)
        self.set_m3u_playlist()
        
        # Start the Stations
        for i in range(0,nb_stations):
            self.stations[i].start()


class Producer(Thread):
    """a DeeFuzzer Producer master thread"""

    def __init__(self, q):
        Thread.__init__(self)
        self.q = q

    def run(self):
        i=0
        q = self.q
        while 1: 
            q.put(i,1)
            i+=1


class Station(Thread):
    """a DeeFuzzer shouting station thread"""

    def __init__(self, station, q, buffer_size, logger):
        Thread.__init__(self)
        self.station = station
        self.q = q
        self.buffer_size = buffer_size
        self.logger = logger
        self.channel = shout.Shout()
        self.id = 999999
        self.counter = 0
        self.index_list = []
        self.command = 'cat '
        self.delay = 0
        # Media
        self.media_dir = self.station['media']['dir']
        self.channel.format = self.station['media']['format']
        self.mode_shuffle = int(self.station['media']['shuffle'])
        self.bitrate = self.station['media']['bitrate']
        self.ogg_quality = self.station['media']['ogg_quality']
        self.samplerate = self.station['media']['samplerate']
        self.voices = self.station['media']['voices']
        self.rss_dir = self.station['media']['rss_dir']
        self.rss_enclosure = self.station['media']['rss_enclosure']
        # Infos
        self.short_name = self.station['infos']['short_name']
        self.channel.name = self.station['infos']['name']
        self.channel.genre = self.station['infos']['genre']
        self.channel.description = self.station['infos']['description']
        self.channel.url = self.station['infos']['url']
        self.base_name = self.rss_dir + os.sep + self.short_name + '_' + self.channel.format
        self.rss_current_file = self.base_name + '_current.xml'
        self.rss_playlist_file = self.base_name + '_playlist.xml'
        self.m3u_playlist_file = self.rss_dir + os.sep + self.short_name + '.m3u'
        self.media_url_dir = '/media/'
        # Server
        self.channel.protocol = 'http'     # | 'xaudiocast' | 'icy'
        self.channel.host = self.station['server']['host']
        self.channel.port = int(self.station['server']['port'])
        self.channel.user = 'source'
        self.channel.password = self.station['server']['sourcepassword']
        self.channel.mount = '/' + self.short_name + '.' + self.channel.format
        self.channel.public = int(self.station['server']['public'])
        self.channel.audio_info = { 'bitrate': self.bitrate,
                                    'samplerate': self.samplerate,
                                    'quality': self.ogg_quality,
                                    'channels': self.voices,}
        self.set_playlist()
        self.lp = len(self.playlist)
        self.channel.open()
        # Logging
        self.logger.write('Opening ' + self.short_name + ' - ' + self.channel.name + \
                ' (' + str(self.lp) + ' tracks)...')

    def update_rss(self, media_list, rss_file):
        rss_item_list = []
        if not os.path.exists(self.rss_dir):
            os.makedirs(self.rss_dir)

        if len(media_list) == 1:
            sub_title = '(currently playing)'
        else:
            sub_title = '(playlist)'

        channel_subtitle = self.channel.name + ' ' + sub_title

        for media in media_list:
            media_description = '<table>'
            media_description_item = '<tr><td>%s:   </td><td><b>%s</b></td></tr>'
            for key in media.metadata.keys():
                if media.metadata[key] != '':
                    media_description += media_description_item % (key.capitalize(), media.metadata[key])
            media_description += media_description_item % ('Duration', str(media.length).split('.')[0])
            media_description += media_description_item % ('Bitrate', str(media.bitrate) + ' kbps')
            media_description += '</table>'
            media_stats = os.stat(media.media)
            media_date = time.localtime(media_stats[8])
            media_date = time.strftime("%a, %d %b %Y %H:%M:%S +0000", media_date)
            date_now = str(datetime.datetime.now())

            title = media.metadata['title']
            artist = media.metadata['artist']
            if not (title or artist):
                song = str(media.file_title)
            else:
                song = artist + ' : ' + title

            if self.rss_enclosure == '1':
                media_link = self.channel.url + self.media_url_dir + media.file_name
                media_link = media_link.decode('utf-8')
                rss_item_list.append(PyRSS2Gen.RSSItem(
                    title = song,
                    link = media_link,
                    description = media_description,
                    enclosure = PyRSS2Gen.Enclosure(media_link, str(media.size), 'audio/mpeg'),
                    guid = PyRSS2Gen.Guid(media_link),
                    pubDate = media_date,)
                    )
            else:
                media_link = self.channel.url
                rss_item_list.append(PyRSS2Gen.RSSItem(
                    title = song,
                    link = media_link,
                    description = media_description,
                    guid = PyRSS2Gen.Guid(media_link),
                    pubDate = media_date,)
                    )

        rss = PyRSS2Gen.RSS2(title = channel_subtitle,
                            link = self.channel.url,
                            description = self.channel.description.decode('utf-8'),
                            lastBuildDate = date_now,
                            items = rss_item_list,)

        f = open(rss_file, 'w')
        rss.write_xml(f, 'utf-8')
        f.close()

    def set_playlist(self):
        file_list = []
        for root, dirs, files in os.walk(self.media_dir):
            for file in files:
                s = file.split('.')
                ext = s[len(s)-1]
                if ext.lower() == self.channel.format and not '/.' in file:
                    file_list.append(root + os.sep + file)
        file_list.sort()
        self.playlist = file_list

    def get_next_media(self):
        # Init playlist
        if self.lp != 0:
            self.set_playlist()
            lp_new = len(self.playlist)
            self.logger.write(self.playlist)

            if lp_new != self.lp or self.counter == 0:
                self.id = 0
                self.lp = lp_new
                self.index_list = range(0,self.lp)
                if self.mode_shuffle == 1:
                    # Shake it, Fuzz it !
                    random.shuffle(self.index_list)
                self.logger.write('Station ' + self.short_name + \
                                 ' : generating new playlist (' + str(self.lp) + ' tracks)')
                self.update_rss(self.media_to_objs(self.playlist), self.rss_playlist_file)
            # Or follow...
            else:
                self.id = (self.id + 1) % self.lp

            return self.playlist[self.index_list[self.id]]

    def log_queue(self, it):
        self.logger.write('Station ' + self.short_name + ' eated one queue step: '+str(it))

    def media_to_objs(self, media_list):
        media_objs = []
        for media in media_list:
            file_name, file_title, file_ext = get_file_info(media)
            if file_ext.lower() == 'mp3':
                media_objs.append(Mp3(media))
            elif file_ext.lower() == 'ogg':
                media_objs.append(Ogg(media))
        return media_objs

    def core_process_stream(self, media):
        """Read media and stream data through a generator.
        Taken from Telemeta (see http://telemeta.org)"""

        command = self.command + '"' + media + '"'

        proc = subprocess.Popen(command,
                    shell = True,
                    bufsize = self.buffer_size,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    close_fds = True)

        # Core processing
        while True:
            __chunk = proc.stdout.read(self.buffer_size)
            status = proc.poll()
            if status != None and status != 0:
                raise DeeFuzzerStreamError('Command failure:', command, proc)
            if not __chunk:
                break
            yield __chunk

    def core_process_read(self, media):
        """Read media and stream data through a generator.
        Taken from Telemeta (see http://telemeta.org)"""

        m = open(media, 'r')
        while True:
            __chunk = m.read(self.buffer_size)
            if not __chunk:
                break
            yield __chunk
        m.close()

    def run(self):
        q = self.q
        while True:
            it = q.get(1)
            if self.lp == 0:
                self.logger.write('Error : Station ' + self.short_name + ' have no media to stream !')
                break
            media = self.get_next_media()
            self.counter += 1
            q.task_done()

            it = q.get(1)
            if os.path.exists(media) and not os.sep+'.' in media:
                try:
                    self.current_media_obj = self.media_to_objs([media])
                except:
                    self.logger.write('Error : Station ' + self.short_name + ' : ' + media + 'not found !')
                    break

                title = self.current_media_obj[0].metadata['title']
                artist = self.current_media_obj[0].metadata['artist']
                if not (title or artist):
                    song = str(self.current_media_obj[0].file_name)
                else:
                    song = artist + ' : ' + title

                self.channel.set_metadata({'song': str(song.encode('utf-8')), 'charset': 'utf8',})
                self.update_rss(self.current_media_obj, self.rss_current_file)
                self.logger.write('DeeFuzzing this file on %s :  id = %s, index = %s, name = %s' \
                    % (self.short_name, self.id, self.index_list[self.id], self.current_media_obj[0].file_name))

                stream = self.core_process_read(media)
                q.task_done()

                for __chunk in stream:
                    it = q.get(1)
                    try:
                        self.channel.send(__chunk)
                        self.channel.sync()
                        # self.logger.write('Station delay (ms) ' + self.short_name + ' : '  + str(self.channel.delay()))
                    except:
                        self.logger.write('ERROR : Station %s : could not send the buffer... ') % self.short_name
                    q.task_done()
                stream.close()

        self.channel.close()


def main():
    if len(sys.argv) == 2:
        d = DeeFuzzer(sys.argv[1])
        d.start()
    else:
        text = prog_info()
        sys.exit(text)

if __name__ == '__main__':
    main()