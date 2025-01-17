import xbmc
import xbmcaddon
import xbmcvfs
import xbmcgui
import json
import xml.etree.ElementTree as ElTr
from xml.dom import minidom
import os
import re
from datetime import datetime

addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
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
    xbmc.log('[%s %s] %s' % (addon_id, addon_version, msg), level=level)


def cleanup_xml(xml_string):
    nfo_lines = xml_string.splitlines()
    new_lines = []

    # remove unwanted empty lines from nfo (different behaviour in Win and Linux)
    # remove temporary root tag and one indent
    for line in nfo_lines:
        line = re.sub('</?nfo[^>]*?>', '', str(line))
        if line.strip(): new_lines.append(line.replace('\t<', '<'))
    try:
        return '\n'.join(new_lines)
    except TypeError:
        return b'\n'.join(new_lines)


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
        log("System.OnQuit received: %s, exiting application" % data)
        try:
            exit(0)
        except SystemExit:
            pass

    def onNotification(self, sender, method, data):
        self.methodDict.get(method, self.err)(method, data)

    def videolibrary_onupdate(self, method, data):
        log("Notification received: %s - %s" % (method, data))
        j_data = json.loads(data)

        try:
            item = j_data.get('item', None)
            if item is None:
                raise KeyError('Not all required data included in JSON query')
            elif j_data.get('playcount', None) is None:
                raise KeyError('Missing playcount data in JSON query')

            elif item['type'] == 'movie':
                details = "moviedetails"
                nfo_root = 'movie'
                query = {"method": "VideoLibrary.GetMovieDetails", "params": {"movieid": item['id'], "properties": ["file"]}}
            elif item['type'] == 'musicvideo':
                details = "musicvideodetails"
                nfo_root = 'musicvideo'
                query = {"method": "VideoLibrary.GetMusicVideoDetails", "params": {"musicvideoid": item['id'], "properties": ["file"]}}
            elif item['type'] == 'episode':
                details = "episodedetails"
                nfo_root = 'episodedetails'
                query = {"method": "VideoLibrary.GetEpisodeDetails", "params": {"episodeid": item['id'], "properties": ["file", "episode"]}}
            else:
                raise KeyError('Video library type \'%s\' not supported' % item['type'])

            result = jsonrpc(query)
            if result is not None:
                self.update_nfo(result[details], j_data['playcount'], item['type'], nfo_root)

        except KeyError as e:
            log('Key error: %s' % e, level=xbmc.LOGWARNING)
            return False

    @staticmethod
    def update_nfo(data, playcount, data_type, nforoot):

        nfo = "%s.nfo" % os.path.splitext(data['file'])[0]

        if data_type == 'movie' and not xbmcvfs.exists(nfo):
            log('No %s for file "%s", try movie.nfo' % (nfo, data['file']))
            nfo = os.path.join(os.path.dirname(data['file']), 'movie.nfo')

        if not xbmcvfs.exists(nfo):
            log('No %s for file "%s"' % (nfo, data['file']))
            raise FileNotFoundError

        try:
            with xbmcvfs.File(nfo, 'r') as nfo_file: nfo_xml = nfo_file.read()

            # make Kodi's NFOs valid by adding a temporal root element as multiepisode NFOs are malformed XMLs
            xml = ElTr.ElementTree(ElTr.fromstring(re.sub(r"(<\?xml[^>]+\?>)", r"\1<nfo>", nfo_xml) + "</nfo>"))
            root = xml.getroot()
            for tag in root.findall(nforoot):

                # find episode number in episode of single/multiepisode or modify other nfo
                if tag.find('episode') is None or (tag.find('episode') is not None and tag.find('episode').text == str(data.get('episode', None))):

                    # looking for tag 'watched', create it if necessary and set content depending on playcount
                    xml_watched = ElTr.SubElement(tag, 'watched') if tag.find('watched') is None else tag.find('watched')
                    xml_watched.text = "true" if playcount > 0 else "false"

                    # add 'lastplayed' element if playcount > 0
                    if playcount > 0:
                        xml_lastplayed = ElTr.SubElement(tag, 'lastplayed') if tag.find('lastplayed') is None else tag.find('lastplayed')
                        xml_lastplayed.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        if tag.find('lastplayed') is not None: tag.remove(tag.find('lastplayed'))

                    # looking for tag 'playcount' create it if necessary and set content with playcount
                    xml_playcount = ElTr.SubElement(tag, 'playcount') if tag.find('playcount') is None else tag.find('playcount')
                    xml_playcount.text = str(playcount)

            # convert to pretty formatted xml, remove temporal root element and write out
            pretty_xml = minidom.parseString(ElTr.tostring(root)).toprettyxml(indent='\t', newl=os.linesep)
            with xbmcvfs.File(nfo, 'w') as f:
                result = f.write(cleanup_xml(pretty_xml))
            if result:
                log('NFO %s written.' % nfo)
                return True
            else:
                xbmcgui.Dialog().notification(addon_name, 'NFO update/creation failed.', xbmcgui.NOTIFICATION_ERROR)
                raise PermissionError('NFO update/creation failed.')

        except (ElTr.ParseError, FileNotFoundError, PermissionError) as e:
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
