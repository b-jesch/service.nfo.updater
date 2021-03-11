import xbmc, xbmcaddon
import xbmcvfs
import json
import xml.etree.ElementTree as EleTree
from os import path

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
                           }

    @staticmethod
    def err(data):
        log("Could not proceed: %s" % data)

    def onNotification(self, sender, method, data):
        log("Notification received: %s - %s" % (method, data))
        self.methodDict.get(method, self.err)(data)

    def videolibrary_onupdate(self, json_data):
        data = json.loads(json_data)
        item = data['item']

        if item['type'] == 'movie':
            mediaquery = "VideoLibrary.GetMovieDetails"
            mediatype = "movieid"
            details = "moviedetails"
        elif item['type'] == 'episode':
            mediaquery = "VideoLibrary.GetEpisodeDetails"
            mediatype = "episodeid"
            details = "episodedetails"
        else:
            log('Could not determine media type: %s' % item['type'], level=xbmc.LOGERROR)
            return False

        query = {"method": mediaquery, "params": {mediatype: item['id'], "properties": ["file"]}}
        result = jsonrpc(query)
        if result is not None:
            self.update_nfo(result[details], data['playcount'])

    @staticmethod
    def update_nfo(data, playcount):

        nfo = "%s.nfo" % path.splitext(data['file'])[0]

        if not xbmcvfs.exists(nfo):
            log('No NFO for file "%s"' % data['file'])
            return False

        with xbmcvfs.File(nfo) as f: xml = EleTree.ElementTree(EleTree.fromstring(f.read()))
        root = xml.getroot()

        # looking for tag 'watched', create it if necessary and set content depending of playcount
        xml_watched = EleTree.SubElement(root, 'watched') if root.find('watched') is None else root.find('watched')
        xml_watched.text = "true" if playcount > 0 else "false"

        # looking for tag 'playcount' create it if necessary and set content with playcount
        xml_playcount = EleTree.SubElement(root, 'playcount') if root.find('playcount') is None else root.find('playcount')
        xml_playcount.text = str(playcount)

        with xbmcvfs.File(nfo, 'w') as f: f.write(EleTree.tostring(root))
        log('NFO %s written.' % nfo)

    # main loop
    
    def main(self):
        while not self.abortRequested():
            xbmc.sleep(10000)


if __name__ == '__main__':
    service = NFOUpdater()
    service.main()
    del service
