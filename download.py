import sys
import csv
import argparse
import subprocess
import shlex
import random
import textwrap
import re


def print_format():
    print("Txt file format.\n\
    File starts with a header, which contains the playlist index.\n\
    Below that are all the playlists. Each entry in a playlist needs at least 3 spaces between fields.\n\
    All empty lines and lines starting with a `#' are ignored.\n\
    If `SKIP' is found on a line, all songs until `END SKIP' line are skipped, or all remaining in the current playlist if `END SKIP' is not found until then.\n\
    \n\
    FILE.txt:\n\
    \n\
    INDEX PLAYLISTS\n\
    - <playlist name>\n\
    - <playlist name>\n\
    ...\n\
    - <playlist name>\n\
    END INDEX\n\
    \n\
    END HEADER\n\
    \n\
    PLAYLIST <playlist name>\n\
    <title>        <artists>        <album>            [<link>]\n\
    <title>        <artists>        <album>            [<link>]\n\
    <title>        <artists>        <album>            [<link>]\n\
    <title>        <artists>        <album>            [<link>]\n\
    ...\n\
    \n\
    PLAYLIST <playlist name>\n\
    <title>        <artists>        <album>            [<link>]\n\
    <title>        <artists>        <album>            [<link>]\n\
    ...\n\
    \n\
    ...\n\
    \n\n\
Csv file format. (excel format)\n\
    FILE.csv:\n\n\
    playlist, title, artists, album, link\n\
    <entry>\n\
    <entry>\n\
    ...\n\
    ")


parser = argparse.ArgumentParser(
    prog="download.py",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description="Download songs specified in a txt/csv file, or convert txt to csv file.",
    epilog=textwrap.dedent('''\
        Required dependencies:
            - yt-dlp (youtube-dl fork). Github: https://github.com/yt-dlp/yt-dlp
            - ffmpeg. Website: https://ffmpeg.org/
        
        Github page: <blank>
    ''')
    #"Dependencies: yt-dlp (youtube-dl fork): https://github.com/yt-dlp/yt-dlp and ffmpeg: https://ffmpeg.org/"
)
parse_group = parser.add_mutually_exclusive_group(required=True)
parse_group.add_argument('-c', '--convert', action='store_true', help='Converts a txt file to a csv file. Fields should be in the same order as the csv. Use -f flag for info on format.')
parse_group.add_argument('-d', '--dl', '--download', action='store_true', help="Download all songs specified in a txt/csv file. Use -f flag for info on format. \
For each playlist it will create a new folder in the output directory with the playlist name. Uncategorised songs are placed in the root folder. Songs where download link is not specified are skipped.")
parse_group.add_argument('-f', '--format', action='store_true', help="Display format of the txt/csv files and exit.")

parser.add_argument('--csv', action='store', help='Csv file. When -c is set, this is the output file. Otherwise treated as input file.')
parser.add_argument('--txt', action='store', help='Txt input file. This is prioritised when downloading if --csv is also specified.')
parser.add_argument('--dir', '--directory', action='store', help='Output directory. Ignored if -d is not set.')

parser.add_argument('-s', '--sd', '--skip-duplicates', action='store_true', help="Skip songs that were already specified in a playlist. Song is only filtered if the titel+artists combination is already parsed.")
parser.add_argument('--filter-playlists', action='store', default=None, help="Only download specified playlists, as a comma-separated list of playlist names. E.g. `FOO,BAR'. Set -i to use a list of playlist indices instead.")
parser.add_argument('-i', '--indices', action='store_true', help="Only has effect if --filter-playlists is set. Playlists are parsed instead as indices (starting from 0) in the playlist overview. \
This option only works with the txt file input. It is ignored on csv input.")
parser.add_argument('--ignore-noplaylist', action='store_true', help="Ignore all songs that are not in a playlist. If not set, these songs will be downloaded even if filtering by playlists with -p.")
parser.add_argument('--ffmpeg-location', action='store', default="C:/Program Files/ffmpeg/ffmpeg.exe", 
                    help="Location of the ffmpeg installation used to convert between file types. (default: C:/Program Files/ffmpeg/ffmpeg.exe)")
parser.add_argument('--config-location', action='store', default='./ytdlp.conf', help="yt-dlp config path. (default: ./ytdlp.conf)")
parser.add_argument('--ytdlp-cmd', action='store', default='C:/Program Files/ytdlp/yt-dlp.exe', help="Command to run ytdlp. (default: 'C:\\Program Files\\ytdlp\\yt-dlp.exe')")
parser.add_argument('-o', '--output', action='store', default="%%(artists) -- %%(title)", help="Music file output format. '%%(field)' will be replaced with value, where field can be title/artists/album/playlist/link. \
Because this is python, you should enter it with a double '%%': '%%%%(field)'. \
Special characters not allowed in file names are stripped, where '\\', '|', and '/' become ' - '. (default: '%%(artists) --  %%(title)')")
parser.add_argument('-p', '--playlist', action='store_true', help="Create a playlist file (.m3u8) for each playlist. This option does nothing yet.")

parser.add_argument('-v', '--verbose', action='count', default=0, help="Output more detailed log output.")
parser.add_argument('--quiet', action='store_true', help="Output nothing to console. This option overwrites -v")


class Song:
    def __init__(self, title, artists, album, playlist, link):
        self.title = title
        self.artists = artists
        self.album = album
        self.playlist = playlist
        self.link = link

class Debug:
    quiet = False
    verbosity = 0

    @classmethod
    def print(cls, msg='', verbosity=1):
        if not cls.quiet and cls.verbosity >= verbosity:
            print(msg)

def main():

    args = parser.parse_args()

    if args.format:
        print_format()
        exit(0)

    verbosity = args.verbose
    is_quiet = args.quiet
    Debug.quiet = is_quiet
    Debug.verbosity = verbosity
    
    opt_skip_dupes = args.sd
    opt_playlists = args.filter_playlists
    opt_indices = args.indices
    opt_ignore_noplaylist = args.ignore_noplaylist
    opt_ffmpeg_location = args.ffmpeg_location
    opt_conf_location = args.config_location
    opt_ytdlpcmd = args.ytdlp_cmd
    opt_outputformat = args.output
    opt_createplaylistfile = args.playlist

    opt_txtfile = args.txt
    opt_csvfile = args.csv
    opt_outdir = args.dir

    if args.convert and (opt_txtfile == None or opt_csvfile == None):
        print('txt or csv file is missing for converting. Use --csv <file> or --txt <file>. --help for more information.')
        exit(1)
    if args.dl and opt_txtfile == None and opt_csvfile == None:
        print('No txt/csv file provided to download from. Use --csv <file> and --txt <file>. --help for more information.')
        exit(1)
    if args.dl and opt_outdir == None:
        print('No output directory specified to download to. Use --dir <path>. --help for more information.')
        exit(1)
    
    if args.convert:
        songs, stats = read_txtfile(opt_txtfile, opt_playlists, opt_indices, opt_ignore_noplaylist, opt_skip_dupes)
        print_parsestats(stats, False)
        write_csvfile(opt_csvfile, songs)
        
    elif args.dl and opt_txtfile != None:
        songs, stats = read_txtfile(opt_txtfile, opt_playlists, opt_indices, opt_ignore_noplaylist, opt_skip_dupes)
        print_parsestats(stats, True)
        download_songs(songs, opt_outdir, opt_outputformat, opt_createplaylistfile, opt_ytdlpcmd, opt_ffmpeg_location, opt_conf_location)
    elif args.dl and opt_csvfile != None:
        songs, stats = read_csvfile(opt_csvfile, opt_playlists, opt_ignore_noplaylist, opt_skip_dupes)
        print_parsestats(stats, True)
        download_songs(songs, opt_outdir, opt_outputformat, opt_createplaylistfile, opt_ytdlpcmd, opt_ffmpeg_location, opt_conf_location)

# total, skipped_total, skipped_noplaylist, ignore_noplaylist, skipped_notallowed, allowed_playlists, nolink, skipped_dupes, skip_dupes
def print_parsestats(stats, isdownload=False):
    verbosity = 0
    Debug.print('\nSTATS:\n-----------------', verbosity)
    if stats['ignore_noplaylist']:
        Debug.print(f"--ignore-noplaylist is set: {stats['skipped_noplaylist']}/{stats['total']} songs skipped.", verbosity)
    if stats['allowed_playlists'] != None:
        Debug.print(f"--filter-playlists is set: {stats['skipped_notallowed']}/{stats['total']} songs skipped.", verbosity)
    if stats['skip_dupes']:
        Debug.print(f"--skip-duplicates is set: {stats['skipped_dupes']}/{stats['total']} duplicates were skipped.", verbosity)
    if stats['skipped_skip'] > 0:
        Debug.print(f"One or more `SKIP' keywords were found. {stats['skipped_skip']}/{stats['total']} were skipped.", verbosity)
    if isdownload:
        if stats['nolink'] > 0:
            Debug.print(f"{stats['nolink']}/{stats['total']} do not have a link specified and were skipped.", verbosity)
        Debug.print(f"{stats['skipped_total'] + stats['nolink']}/{stats['total']} songs were skipped overall.", verbosity)
    else:
        if stats['nolink'] > 0:
            Debug.print(f"Warning: {stats['nolink']} songs did not have a link specified, and will be skipped if trying to download.", verbosity)
        Debug.print(f"{stats['skipped_total']}/{stats['total']} songs were skipped overall.", verbosity)
    Debug.print('-----------------\n', verbosity)

def parse_txtheader(lines):
    parsing_header = True
    playlists = []
    reading_index = False

    # parse header of the file
    i = 0
    while parsing_header and i < len(lines):
        line = lines[i].strip()
        i += 1

        # parse the header of the file
        if len(line) == 0 or line[0] == '#':
            continue
        if line == 'INDEX PLAYLISTS':
            reading_index = True
        elif reading_index and line[:2] == "- ":
            playlists.append(line[2:])
        elif line == 'END INDEX':
            reading_index = False
        elif line == 'END HEADER':
            if reading_index:
                Debug.print('End of header encountered before end of index. Stopping reading playlist index.', 2)
            parsing_header = False
    Debug.print('Playlists found in header:', 1)
    for playlist in playlists:
        Debug.print(f'- {playlist}', 1)
    Debug.print('\n', 1)
    return (playlists, i)

def parse_txtsongs(lines, i, allowed_playlists=None, ignore_noplaylist=False, skip_dupes=False):
    songs = []
    curr_playlist = ""
    total = 0
    nolink = 0
    skipped_noplaylist = 0
    skipped_notallowed = 0
    skipped_dupes = 0
    skipped_total = 0
    skipped_skip = 0

    skipping_songs = False

    playlist_songs = []

    while i < len(lines):
        trimmed_line = lines[i].strip()
        i += 1

        if trimmed_line[:8] == "PLAYLIST":
            Debug.print("\nplaylist %s" % trimmed_line[9:], 2)
            curr_playlist = trimmed_line[9:].replace("\"", "\"\"")
            playlist_songs = []
            skipping_songs = False
        elif trimmed_line == "SKIP":
            skipping_songs = True
        elif trimmed_line == "END SKIP":
            skipping_songs = False
        elif len(trimmed_line) != 0 and trimmed_line[0] != '#':
            # line is not empty or comment

            total += 1


            # escape double quotes to not break csv file and split fields
            metadata = list(filter(lambda x: len(x) != 0, trimmed_line.replace("\"", "\"\"").split("   ")))
            # parse metadata
            title = metadata[0].strip()
            artists = ""
            if len(metadata) > 1:
                artists = metadata[1].strip()
            album = ""
            if len(metadata) > 2:
                album = metadata[2].strip()
            link = ""
            if len(metadata) > 3:
                # dl link is specified in txt file
                link = metadata[3].strip()
            
            if link == None or link == "":
                nolink += 1
            
            shouldSkip = False
            if skipping_songs:
                Debug.print(f'Skipping song because SKIP keyword was encountered.', 2)
                skipped_skip += 1
                shouldSkip = True
            
            if curr_playlist == "" and ignore_noplaylist:
                Debug.print(f'Skipping song with no playlist.', 2)
                skipped_noplaylist += 1
                shouldSkip = True

            if curr_playlist != "" and allowed_playlists != None and curr_playlist not in allowed_playlists:
                Debug.print(f'Skipping song that is not in allowed playlists.', 2)
                skipped_notallowed += 1
                shouldSkip = True
            
            if skip_dupes:
                if (title + artists) in playlist_songs:
                    Debug.print(f'Song with same title and artists already found. Skipping duplicate song in playlist.', 2)
                    skipped_dupes += 1
                    shouldSkip = True
                else:
                    playlist_songs.append(title + artists)

            

            if shouldSkip:
                Debug.print(f'Skipping song: {curr_playlist} | {title} | {artists} | {album} | {link}', 2)
                skipped_total += 1
                continue

            song = Song(title, artists, album, curr_playlist, link)
            Debug.print(f"playlist: {song.playlist} | song: {song.title} | artists: {song.artists} | album: {song.album} | link: {song.link}", 2)
            songs.append(song)
    
    stats = {
        'total': total,
        'skipped_total': skipped_total,
        'skipped_noplaylist': skipped_noplaylist,
        'ignore_noplaylist': ignore_noplaylist,
        'skipped_notallowed': skipped_notallowed,
        'allowed_playlists': allowed_playlists,
        'nolink': nolink,
        'skipped_dupes': skipped_dupes,
        'skip_dupes': skip_dupes,
        'skipped_skip': skipped_skip
    }
    return (songs, stats)



def read_txtfile(txtfile, allowed_playlists=None, use_indices=False, ignore_noplaylist=False, skip_dupes=False):
    Debug.print('Reading from TXT...\n\n', 0)
    lines = []
    try:
        reader = open(txtfile, 'r', encoding='utf-8')
    except IOError as err:
        Debug.print("Txt file could not be opened to read from.", 0)
        exit(3)
    else:
        with reader:
            lines = reader.readlines()
    

    playlists, i = parse_txtheader(lines)
    
    if allowed_playlists != None and use_indices:
        allowed_playlists = list(map(lambda x: playlists[int(x)] if int(x) < len(playlists) else None, allowed_playlists))

    return parse_txtsongs(lines, i, allowed_playlists, ignore_noplaylist, skip_dupes)


def write_csvfile(csvfile, songs):
    Debug.print('Writing to CSV...\n\n', 0)
    try:
        writer = open(csvfile, 'w', encoding='utf-8', newline='')
    except IOError as err:
        print("csv file could not be opened to write to.")
        exit(4)
    else:
        with writer:
            dictwriter = csv.DictWriter(writer, ['playlist', 'title', 'artists', 'album', 'link'])
            dictwriter.writeheader()
            csvwriter = csv.writer(writer)
            try:
                for song in songs:
                    csvwriter.writerow([song.playlist, song.title, song.artists, song.album, song.link])
                    Debug.print(f"playlist: {song.playlist} | song: {song.title} | artists: {song.artists} | album: {song.album} | link: {song.link}", 2)
            except csv.Error as e:
                sys.exit('file {}, line {}: {}'.format(csvfile, csvwriter.line_num, e))


def read_csvfile(csvfile, allowed_playlists=None, ignore_noplaylist=False, skip_dupes=False):
    Debug.print('Reading from CSV...\n\n', 0)
    try:
        reader = open(csvfile, 'r', encoding='utf-8', newline='')
    except IOError as err:
        print("csv file could not be opened to read from.")
        exit(4)
    else:
        songs = []
        total = 0
        skipped_total = 0
        nolink = 0
        skipped_noplaylist = 0
        skipped_notallowed = 0
        skipped_dupes = 0

        song_dict = {}

        with reader:
            csvreader = csv.DictReader(reader, ['playlist', 'title', 'artists', 'album', 'link'])
            try:
                # skip header
                next(csvreader, None)
                for row in csvreader:
                    total += 1
                    playlist = row['playlist']
                    title = row['title']
                    artists = row['artists']
                    album = row['album']
                    link = row['link']

                    if link == None or link == "":
                        nolink += 1
                    

                    shouldskip = False

                    
                    if playlist == None and ignore_noplaylist:
                        Debug.print(f'Skipping song with no playlist.', 2)
                        skipped_noplaylist += 1
                        shouldskip = True
                    if playlist != None and allowed_playlists != None and playlist not in allowed_playlists:
                        Debug.print(f'Skipping song that is not in allowed playlists.', 2)
                        skipped_notallowed += 1
                        shouldskip = True
                    
                    # store songs into dictionary to catch duplicates (but only add them if not skipping)
                    if playlist not in song_dict:
                        if not shouldskip:
                            song_dict[playlist] = [title + artists]
                    elif (title + artists) in song_dict[playlist] and skip_dupes:
                        Debug.print(f'Song with same title and artists already found. Skipping duplicate song in playlist.', 2)
                        skipped_dupes += 1
                        shouldskip = True
                    elif not shouldskip:
                        song_dict[playlist].append(title + artists)

                    if shouldskip:
                        Debug.print(f'Skipping song: {playlist} | {title} | {artists} | {album} | {link}', 2)
                        skipped_total += 1
                        continue
                    

                    songs.append(Song(title, artists, album, playlist, link))
            except csv.Error as e:
                sys.exit('file {}, line {}: {}'.format(csvfile, csvreader.line_num, e))
        
        stats = {
            'total': total,
            'skipped_total': skipped_total,
            'skipped_noplaylist': skipped_noplaylist,
            'ignore_noplaylist': ignore_noplaylist,
            'skipped_notallowed': skipped_notallowed,
            'allowed_playlists': allowed_playlists,
            'nolink': nolink,
            'skipped_dupes': skipped_dupes,
            'skip_dupes': skip_dupes,
            'skipped_skip': 0 # CSV file cannot contain SKIP keyword, so this is always 0
        }
        return songs, stats


def filter_filedir_str(str):
    return re.sub("[\\\\\\|\\/]", " - ", re.sub('["\\?\\*<>]', "", str)).strip()

def generate_playlistdir(song):
    if song.playlist != "":
        album_dir = filter_filedir_str(song.playlist)
        # album_dir = "".join(c for c in song.playlist if c.isalnum() or c in keepcharacters).rstrip()
        if album_dir == "":  
            # generate random playlist name if the playlist name has no allowed dir characters.
            album_dir = f"playlist_{random.randrange(0, 100000)}"
        return album_dir
    return ""


def download_songs(songs, outdir, outputformat, createplaylistfile, ytdlpcmd, ffmpegpath, configpath):
    errors = 0
    for song in songs:
        if song.link != None and song.link != "":
            playlistdir = generate_playlistdir(song)
            returncode = run_ytdlp_on_song(song, outdir + "/" + playlistdir, outputformat, ytdlpcmd, ffmpegpath, configpath)
            if returncode != 0:
                errors += 1
                Debug.print(f'An error (code {returncode}) occurred downloading song: {song.title} | {song.artists} | {song.album} | {song.link}', 1)
        else:
            Debug.print(f'Skipping song with no download link: {song.title} | {song.artists} | {song.album}', 2)
    Debug.print(f'\n{len(songs) - errors}/{len(songs)} songs were downloaded correctly.\n', 0)


def parse_outputformat(outputformat, song):
    if outputformat == None or outputformat == "":
        return f'{song.artists} -- {song.title}'
    output = outputformat.replace('%%(title)', song.title).replace('%%(artists)', song.artists).replace('%%(album)', song.album).replace('%%(link)', song.link).replace('%%(playlist)', song.playlist)
    return filter_filedir_str(output)



def run_ytdlp_on_song(song, outdir, outputformat, ytdlpcmd, ffmpegpath, configpath):
    Debug.print(f'Downloading song... {song.playlist} | {song.title} | {song.artists} | {song.album} | {song.link}', 1)
    verbose_opt = ""
    if Debug.quiet:
        verbose_opt = "--quiet "
    elif Debug.verbosity > 1:
        verbose_opt = "-v "

    file_name = parse_outputformat(outputformat, song)
    

    
    # add space add the end for single-word strings, to force it to interpret it as literals
    title = song.title if ' ' in song.title else f'{song.title} '
    artists = song.artists if ' ' in song.artists else f'{song.artists} '
    album = song.album if ' ' in song.album else f'{song.album} '

    # keepcharacters = (' ','.','_')
    full_outdir = outdir
    # if song.playlist != "":
    #     album_dir = filter_filedir_str(song.playlist)
    #     # album_dir = "".join(c for c in song.playlist if c.isalnum() or c in keepcharacters).rstrip()
    #     if album_dir == "":  
    #         # generate random playlist name if the playlist name has no allowed dir characters.
    #         album_dir = f"playlist_{random.randrange(0, 100000)}"
    #     full_outdir = outdir + "/" + album_dir
    

    command = f'{ytdlpcmd} --ffmpeg-location "{ffmpegpath}" \
--embed-metadata --parse-metadata "{title}:%(meta_title)s" --parse-metadata "{artists}:%(meta_artist)s" --parse-metadata "{album}:%(meta_album)s" \
--config-locations "{configpath}" -P "{full_outdir}" -o "{file_name}" {verbose_opt}-- "{song.link}"'
    Debug.print(f'command: {command}\n\n', 2)
    command_args = shlex.split(command)
    proc = subprocess.run(command_args)
    Debug.print(f"\nYT-DLP exited with code {proc.returncode}", 2)
    return proc.returncode

# run_ytdlp_on_song("D_5JQLUyuJ0", "Transgender Dysphoria Blues TITLE", "Against Me! ARTIST", "Transgender Dysphoria Blues ALBUM", "/out", verbose=True)

main()
