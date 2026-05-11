from flask import Flask, request, jsonify
from flask_cors import CORS
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
import re

app = Flask(__name__, static_folder='/home/10wol', static_url_path='')
CORS(app)

YOUTUBE_API_KEY = "AIzaSyA9OCTxbBsv4qP1wmUkbCsi8YB1gfzmBcg"

def extract_handle_or_id(url):
    patterns = [
        (r'youtube\.com/channel/([^/?&\s]+)', 'id'),
        (r'youtube\.com/@([^/?&\s]+)', 'handle'),
        (r'youtube\.com/c/([^/?&\s]+)', 'handle'),
        (r'youtube\.com/user/([^/?&\s]+)', 'handle'),
    ]
    for pattern, kind in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1), kind
    return None, None

def resolve_channel_id(value, kind, api_key):
    yt = build('youtube', 'v3', developerKey=api_key)
    if kind == 'id':
        return value
    res = yt.search().list(part='snippet', q=value, type='channel', maxResults=1).execute()
    if res.get('items'):
        return res['items'][0]['snippet']['channelId']
    return None

def get_videos(channel_id, api_key, max_videos=50):
    yt = build('youtube', 'v3', developerKey=api_key)
    ch = yt.channels().list(part='contentDetails', id=channel_id).execute()
    if not ch.get('items'):
        return []
    uploads_id = ch['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    videos, next_page = [], None
    while len(videos) < max_videos:
        pl = yt.playlistItems().list(
            part='snippet', playlistId=uploads_id,
            maxResults=min(50, max_videos - len(videos)),
            pageToken=next_page
        ).execute()
        for item in pl['items']:
            sn = item['snippet']
            videos.append({
                'id': sn['resourceId']['videoId'],
                'title': sn['title'],
                'thumbnail': sn['thumbnails'].get('medium', {}).get('url', ''),
                'published': sn['publishedAt'][:10]
            })
        next_page = pl.get('nextPageToken')
        if not next_page:
            break
    return videos

def search_transcript(video_id, keyword):
    try:
        tlist = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        for lang in ['ko', 'ko-KR']:
            try:
                transcript = tlist.find_transcript([lang])
                break
            except:
                pass
        if not transcript:
            try:
                transcript = tlist.find_generated_transcript(['ko', 'ko-KR', 'en'])
            except:
                codes = [t.language_code for t in tlist]
                transcript = tlist.find_transcript(codes)
        data = transcript.fetch()
except Exception as e:
        print(f"자막 오류 {video_id}: {e}")
        return []
    kw = keyword.lower()
    hits = []
    for entry in data:
        if kw in entry['text'].lower():
            s = int(entry['start'])
            h, m, sec = s // 3600, (s % 3600) // 60, s % 60
            hits.append({
                'time': s,
                'timeStr': f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}",
                'text': entry['text']
            })
    return hits

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/search', methods=['GET'])
def search():
    channel_url = request.args.get('channel', '').strip()
    keyword = request.args.get('keyword', '').strip()
    if not channel_url or not keyword:
        return jsonify({'error': '채널 URL과 키워드를 모두 입력해주세요.'}), 400
    value, kind = extract_handle_or_id(channel_url)
    if not value:
        return jsonify({'error': '올바른 YouTube 채널 URL이 아니에요.'}), 400
    channel_id = resolve_channel_id(value, kind, YOUTUBE_API_KEY)
    if not channel_id:
        return jsonify({'error': '채널을 찾을 수 없어요.'}), 404
    videos = get_videos(channel_id, YOUTUBE_API_KEY)
    if not videos:
        return jsonify({'error': '영상 목록을 불러올 수 없어요.'}), 404
    results = []
    for v in videos:
        hits = search_transcript(v['id'], keyword)
        if hits:
            results.append({
                'videoId': v['id'],
                'title': v['title'],
                'thumbnail': v['thumbnail'],
                'published': v['published'],
                'hitCount': len(hits),
                'timeline': hits
            })
    return jsonify({
        'keyword': keyword,
        'totalVideos': len(videos),
        'matchedVideos': len(results),
        'results': results
    })
