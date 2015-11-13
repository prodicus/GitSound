# coding=utf-8
from __future__ import unicode_literals, print_function
import spotipy
import spotipy.util
import os
import pygit2
import util


class SpotifyUser(object):

    def __init__(self, username, client_id, client_secret, redirect_uri):
        self.username = username

        # add the scope for things we need, can change over time if we need
        # less
        scope = "playlist-read-private "
        scope += "playlist-read-collaborative "
        scope += "playlist-modify-public "
        scope += "playlist-modify-private "

        # directory that the gitfiles will be stored in
        self.git_dir = ".activePlaylists/"

        # need to write more code to get the author (and comitter)
        # might want to change comitter to local git user
        self.author = pygit2.Signature("spotify username", "spotify email")
        self.comitter = pygit2.Signature("spotify username", "spotify email")

        # gets the token from the spotify api, can not do anything without this
        self.token = spotipy.util.prompt_for_user_token(
            username, client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope)

        # error out if we don't have a token
        if self.token == None:
            raise RuntimeError("Cannot get token from " + username)

        # use the token to create a new spotify session
        self.sp = spotipy.Spotify(auth=self.token)

        # get the current spotify playlists
        self.playlists = self.sp.user_playlists(username)['items']

        self.tree = None
        self.repo = None

    def get_playlist_ids(self):
        ids = []
        for playlist in self.playlists:
            ids.append({"pid": playlist["id"], "uid": playlist["owner"]["id"]})

        # returns a list of ids in the following format
        # '{"pid": foo, "uid": bar}'
        return ids

    def get_playlist_id(self, position):
        position = int(position)
        return {"pid": self.playlists[position]["id"], "uid": self.playlists[position]["owner"]["id"]}

    def get_playlist_names(self):
        names = []
        for playlist in self.playlists:
            names.append(playlist["name"])

        return names

    def get_playlist_name(self, position):
        position = int(position)
        return self.playlists[position]["name"]

    def get_playlist_tracks(self, uid, pid):
        playlistInfo = self.sp.user_playlist(uid, pid)["tracks"]["items"]
        return playlistInfo

    def init_git_playlist(self, uid, pid):

        playlist_path = uid + "/" + pid

        # gets the track list IDs
        trackList = self.get_playlist_tracks(uid, pid)

        # make sure that the directories exist, if not create them
        os.makedirs(self.git_dir, exist_ok=True)
        os.makedirs(self.git_dir + playlist_path, exist_ok=True)

        if os.path.isfile(self.git_dir + playlist_path + "/index.txt"):
            raise RuntimeError("Tried to clone playlist when one of the " +
                               "same playlist has been cloned already.")

        with open(self.git_dir + playlist_path + "/index.txt", "w") as f:
            for track in trackList:
                if track["track"]["id"] != None:  # ignore local files
                    print(track["track"]["id"], file=f)

        # create repo and build tree
        new_repo = pygit2.init_repository(self.git_dir + playlist_path)
        new_tree = new_repo.TreeBuilder().write()

        first_commit = new_repo.create_commit("HEAD", self.author, self.comitter,
                                              "Created master", new_tree, [])

        # create blob for the index file
        file_blob = new_repo.create_blob_fromdisk(
            self.git_dir + playlist_path + "/index.txt")

        # build tree again
        new_tree = new_repo.TreeBuilder()

        # add our new index file
        new_tree.insert("index.txt", file_blob,
                        os.stat(self.git_dir + playlist_path + "/index.txt").st_mode)

        # build tree again
        self.tree = new_tree.write()

        # add the index file to the repo
        new_repo.index.read()
        new_repo.index.add("index.txt")
        new_repo.index.write()

        # commit the file
        new_repo.create_commit(
            "HEAD", self.author, self.comitter, "Added index.txt", self.tree,
            [first_commit])

    def add_song_to_playlist(self, uid, pid, songid):

        playlist_path = uid + "/" + pid

        util.check_if_git_playlist(self.git_dir, playlist_path)

        with open(self.git_dir + playlist_path + "/index.txt", "r+") as f:
            songIds = []
            for line in f.readlines():
                line = line.strip()
                songIds.append(line)

                if songid == line:
                    raise RuntimeError("Song is already in playlist")
            print(songid, file=f)

        # get the repo
        self.repo = pygit2.Repository(self.git_dir + playlist_path)

        # create a new blob for our new index
        file_blob = self.repo.create_blob_fromdisk(
            self.git_dir + playlist_path + "/index.txt")

        # build the tree
        new_tree = self.repo.TreeBuilder()

        # add the index file
        new_tree.insert("index.txt", file_blob,
                        os.stat(self.git_dir + playlist_path + "/index.txt").st_mode)

        self.tree = new_tree.write()

    def remove_song_from_playlist(self, uid, pid, songid):

        playlist_path = uid + "/" + pid

        util.check_if_git_playlist(self.git_dir, playlist_path)

        with open(self.git_dir + playlist_path + "/index.txt", "r+") as f:
            songIds = []
            found_song = False
            for line in f.readlines():
                line = line.strip()

                if songid == line:
                    found_song = True
                else:
                    songIds.append(line)

            if found_song == False:
                raise RuntimeError("playlist does not have song.")

            # go to the start of the text file
            f.seek(0)

            for ID in songIds:
                print(ID, file=f)

            # ignore the rest of the text file (parts that were already there)
            f.truncate()

        self.repo = pygit2.Repository(self.git_dir + playlist_path)

        # create the file blob
        file_blob = self.repo.create_blob_fromdisk(
            self.git_dir + playlist_path + "/index.txt")

        new_tree = self.repo.TreeBuilder()

        # insert it into the tree
        new_tree.insert("index.txt", file_blob,
                        os.stat(self.git_dir + playlist_path + "/index.txt").st_mode)

        self.tree = new_tree.write()

    def commit_changes_to_playlist(self, uid, pid):

        playlist_path = uid + "/" + pid

        util.check_if_git_playlist(self.git_dir, playlist_path)

        # get the repo
        self.repo = pygit2.Repository(self.git_dir + playlist_path)

        # create the file blob
        file_blob = self.repo.create_blob_fromdisk(
            self.git_dir + playlist_path + "/index.txt")

        new_tree = self.repo.TreeBuilder()

        # insert it into the tree
        new_tree.insert("index.txt", file_blob,
                        os.stat(self.git_dir + playlist_path + "/index.txt").st_mode)

        self.tree = new_tree.write()

        # add to commit
        self.repo.index.read()
        self.repo.index.add("index.txt")
        self.repo.index.write()

        # commit changes to playlist
        self.repo.create_commit("HEAD", self.author, self.comitter,
                                "Changes committed to " + playlist_path, self.tree, [self.repo.head.target])

    def pull_spotify_playlist(self, uid, pid):

        playlist_path = uid + "/" + pid

        util.check_if_git_playlist(self.git_dir, playlist_path)

        # grab tracks from spotify from pid
        results = self.sp.user_playlist_tracks(self.username, pid)
        results = results["items"]

        # get just a list of the track ids from the response
        remote_tracks = []
        for track in results:
            if track["track"]["id"] != None:  # only take spotify tracks
                remote_tracks.append(track["track"]["id"])

        # get local track ids
        with open(self.git_dir + playlist_path + "/index.txt") as f:
            local_tracks = f.read().splitlines()

        # merge tracks by adding if not added already. local takes precendence
        # does not preserve position of new remote tracks
        diff = False
        for remoteTrack in remote_tracks:
            if remoteTrack not in local_tracks:
                local_tracks.append(remoteTrack)
                diff = True

        # write tracks back to file
        with open(self.git_dir + playlist_path + "/index.txt", "w") as f:
            for track in local_tracks:
                print(track, file=f)

        # commit playlist changes if needed
        if (diff == True):
            self.commit_changes_to_playlist(uid, pid)
            return 'Added and committed changes from remote.'
        return 'No changes committed, up to date with remote.'

    def song_lookup(self, name=None, artist=None, limit=1):
        results = self.sp.search(q='track:' + name,
                                 type='track',
                                 limit=limit)

        # if no songs found with that name
        if len(results['tracks']['items']) == 0:
            print("No results found for " + name)
            return
            # not sure if we want the above to raise an error/warning or just
            # print out
        else:
            songs = {}
            artists = results['tracks']['items'][0]['artists']
            artist_names = []
            for index, names in enumerate(artists):
                # stores main artist and all the featured artists
                artist_names.append(names['name'])
            songs['artists'] = artist_names
            songs['trackid'] = results['tracks']['items'][0]['id']
            songs['track'] = results['tracks']['items'][0]['name']
            print("Results for " + songs['track'] +
                  ' by ' + songs['artists'][0])

            # dictionary containing track name, artists, and track id
            return songs


if __name__ == "__main__":
    print("gitSound.py is a support libary, please run main.py instead.")
