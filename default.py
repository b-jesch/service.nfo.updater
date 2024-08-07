﻿import xbmc
import xbmcaddon
import xbmcvfs
import json
import xml.etree.ElementTree as ElTr
import os

addon = xbmcaddon.Addon()
addon_name = addon.getAddonInfo('name')
addon_version = addon.getAddonInfo('version')


def jsonrpc(query):
    querystring = {"jsonrpc": "2.0", "id": 1}
    querystring.update(query)
    try:
        response = json.loads(xbmc.executeJSONRPC(json.dumps(querystring)))
        if 'result' in response: return response['result']
    except TypeError as e:
        log('Error executing JSON RPC: {}'.format(e.args), level=xbmc.LOGERROR)
    return None


def log(msg, level=xbmc.LOGDEBUG):
    xbmc.log('[%s %s] %s' % (addon_name, addon_version, msg), level=level)


class NFOUpdater(xbmc.Monitor):
    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)
        log('Monitor started')

        self.methodDict = {"VideoLibrary.OnUpdate": self.videolibrary_onupdate,
                           "System.OnQuit": self.quit,
                           }

    def err(self, method, data):
        log("Discard notification %s" % method)

    def quit(self, method, data):
        log("System.OnQuit received: %s, exiting application" %data)
        exit(0)

    def onNotification(self, sender, method, data):
        self.methodDict.get(method, self.err)(method, data)

    def videolibrary_onupdate(self, method, data):
        log("Notification received: %s - %s" % (method, data))
        j_data = json.loads(data)
        try:
            item = j_data['item']

            if item['type'] == 'movie':
                mediaquery = "VideoLibrary.GetMovieDetails"
                mediatype = "movieid"
                details = "moviedetails"
            elif item['type'] == 'musicvideo':
                mediaquery = "VideoLibrary.GetMusicVideoDetails"
                mediatype = "musicvideoid"
                details = "musicvideodetails"
            elif item['type'] == 'episode':
                mediaquery = "VideoLibrary.GetEpisodeDetails"
                mediatype = "episodeid"
                details = "episodedetails"
            else:
                raise KeyError('Video library type \'%s\' not supported' % item['type'])

            query = {"method": mediaquery, "params": {mediatype: item['id'], "properties": ["file"]}}
            result = jsonrpc(query)

            if result is not None:
                self.update_nfo(result[details], j_data['playcount'], item['type'])

        except KeyError as e:
            log('Key error: %s' % e, level=xbmc.LOGWARNING)
            return False

    @staticmethod
    def update_nfo(data, playcount, data_type):

        nfo = "%s.nfo" % os.path.splitext(data['file'])[0]

        if data_type == 'movie' and not xbmcvfs.exists(nfo):
            log('No %s for file "%s", try movie.nfo' % (nfo, data['file']))
            nfo = os.path.join(os.path.dirname(data['file']), 'movie.nfo')

        if not xbmcvfs.exists(nfo):
            log('No %s for file "%s"' % (nfo, data['file']))
            return False

        try:
            with xbmcvfs.File(nfo, 'r') as f: xml = ElTr.ElementTree(ElTr.fromstring(f.read()))
            root = xml.getroot()

            # looking for tag 'watched', create it if necessary and set content depending on playcount
            xml_watched = ElTr.SubElement(root, 'watched') if root.find('watched') is None else root.find('watched')
            xml_watched.text = "true" if playcount > 0 else "false"

            # looking for tag 'playcount' create it if necessary and set content with playcount
            xml_playcount = ElTr.SubElement(root, 'playcount') if root.find('playcount') is None else root.find('playcount')
            xml_playcount.text = str(playcount)

            try:
                with xbmcvfs.File(nfo, 'w') as f: f.write(ElTr.tostring(root, encoding='utf8',
                                                                        method='xml', xml_declaration=True))
            except TypeError as e:
                log('writing NFO causes an error: %s' % str(e))
                with xbmcvfs.File(nfo, 'w') as f: f.write(ElTr.tostring(root, encoding='utf8', method='xml'))

            log('NFO %s written.' % nfo)
            return True

        except ElTr.ParseError as e:
            log('Error processing NFO: %s' % e.msg, xbmc.LOGERROR)
            return False

    # main loop
    
    def main(self):
        while not self.abortRequested():
            self.waitForAbort(10000)


if __name__ == '__main__':
    service = NFOUpdater()
    service.main()
    del service
