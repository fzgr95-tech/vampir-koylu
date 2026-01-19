from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room, emit
import random
import string
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar_buraya' # Güvenlik için değiştirilmeli
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/')
def index():
    return render_template('index.html')

# Oyun State'i (Bellekte tutulacak)
rooms = {}

def generate_room_code(length=4):
    """Rastgele oda kodu oluşturur"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        if code not in rooms:
            return code

@socketio.on('connect')
def handle_connect():
    """Kullanıcı bağlandığında genel lobiye al ve oda listesini gönder"""
    join_room('global_lobby')
    emit('room_list_update', {'rooms': get_public_rooms()})

def get_public_rooms():
    """Aktif odaların listesini döndür"""
    public_rooms = []
    for code, room in rooms.items():
        public_rooms.append({
            'code': code,
            'name': room.get('name', f'Oda {code}'),
            'has_password': bool(room['password']),
            'player_count': len(room['players']),
            'status': room['game_state']
        })
    return public_rooms

@socketio.on('create_room')
def handle_create_room(data):
    """Oda oluşturma isteği"""
    room_code = generate_room_code()
    password = data.get('password') # Boş olabilir
    vampire_count = int(data.get('vampire_count', 1))
    room_name = data.get('room_name') or f"Oda {room_code}"
    
    rooms[room_code] = {
        'password': password,
        'name': room_name,
        'vampire_count': vampire_count,
        'players': {}, # sid -> {name, role, is_alive, is_admin}
        'game_state': 'lobby', # lobby, day, night, voting
        'messages': []
    }
    
    # Oluşturan kişiyi global lobiden çıkar (client-side join ile odaya girecek)
    leave_room('global_lobby')
    
    # Oda kurucusu otomatik katılır
    join_room(room_code)
    
    # Süre ayarı (saniye cinsinden, varsayılan 60sn)
    duration = int(data.get('duration', 60))
    room = rooms[room_code]
    room['duration'] = duration
    
    emit('room_created', {'room_code': room_code})
    
    # Diğerlerine güncel listeyi duyur
    socketio.emit('room_list_update', {'rooms': get_public_rooms()}, to='global_lobby')

@socketio.on('join_room')
def handle_join_room(data):
    """Odaya katılma isteği"""
    room_code = data.get('room_code')
    password = data.get('password')
    username = data.get('username')
    
    if room_code not in rooms:
        emit('error', {'message': 'Oda bulunamadı!'})
        return
        
    room = rooms[room_code]
    
    # Şifre varsa kontrol et
    if room['password'] and room['password'] != password:
        emit('error', {'message': 'Hatalı şifre!'})
        return
        
    if request.sid in room['players']:
         pass 
    elif len([p for p in room['players'].values() if p['name'] == username]) > 0:
         emit('error', {'message': 'Bu isimde biri zaten var!'})
         return

    # Global lobiden çık, odaya gir
    leave_room('global_lobby')
    join_room(room_code)
    
    # İlk giren admin olur (Normalde create'de belirlenir ama güvenlik için burada da kalsın)
    is_admin = len(room['players']) == 0
    
    room['players'][request.sid] = {
        'name': username,
        'role': None,
        'is_alive': True,
        'is_admin': is_admin,
        'voted_for': None
    }
    
    emit('player_list_update', {'players': room['players']}, to=room_code)
    emit('joined_room', {
        'room_code': room_code, 
        'room_name': room['name'],
        'is_admin': is_admin, 
        'duration': room.get('duration', 60)
    })
    
    # Oda listesini güncelle (Kişi sayısı değişti)
    socketio.emit('room_list_update', {'rooms': get_public_rooms()}, to='global_lobby')

@socketio.on('start_game')
def handle_start_game(data):
    """Oyunu başlatma ve rol dağıtımı"""
    room_code = data.get('room_code')
    room = rooms.get(room_code)
    
    if not room:
        return

    player_ids = list(room['players'].keys())
    total_players = len(player_ids)
    vampire_count = room['vampire_count']
    
    if total_players < vampire_count + 1:
        emit('error', {'message': 'Yeterli oyuncu yok! Vampir sayısından fazla oyuncu olmalı.'})
        return
        
    # Rol Dağıtımı (Ultimate Edition)
    roles_config = {
        'vampire': vampire_count,
        'doctor': 1,
        'seer': 1,
        'traitor': 1 if total_players > 6 else 0 # 6 kişiden fazlaysa Köstebek var
    }
    
    # Kalanlar köylü
    assigned_roles = []
    for role, count in roles_config.items():
        assigned_roles.extend([role] * count)
        
    while len(assigned_roles) < total_players:
        assigned_roles.append('villager')
        
    # Fazla geldiyse kırp (Vampir sayısı artarsa vs)
    assigned_roles = assigned_roles[:total_players]
    
    random.shuffle(player_ids)
    random.shuffle(assigned_roles)
    
    room['night_actions'] = {} # Gece hamleleri için
    
    for i, sid in enumerate(player_ids):
        role_key = assigned_roles[i]
        role_name_map = {
            'vampire': '🧛 VAMPİR',
            'villager': '👨‍🌾 KÖYLÜ',
            'doctor': '💉 DOKTOR',
            'seer': '🔮 MEDYUM',
            'traitor': '🐀 KÖSTEBEK'
        }
        
        room['players'][sid]['role'] = role_key
        room['players'][sid]['is_alive'] = True
        room['players'][sid]['voted_for'] = None
        
        teammates = []
        if role_key == 'vampire' or role_key == 'traitor':
            # Vampirler ve Köstebek birbirini bilir
            teammates = [rooms[room_code]['players'][pid]['name'] for pid in player_ids 
                         if assigned_roles[player_ids.index(pid)] in ['vampire', 'traitor'] and pid != sid]
        
        emit('game_started', {
            'role': role_key, 
            'role_name': role_name_map[role_key],
            'teammates': teammates
        }, room=sid)

    # Gündüz Evresi Başlat
    start_day_phase(room_code)

def start_day_phase(room_code):
    room = rooms.get(room_code)
    if not room: return
    
    room['game_state'] = 'day'
    duration = room.get('duration', 60)
    
    # Kaos Kartı Seçimi (Her gün %50 şans)
    chaos_event = None
    if random.random() < 0.5:
        chaos_events = [
            {'id': 'blind_vote', 'desc': 'KÖR ADALET: Bu tur oylar gizli olacak!'},
            {'id': 'silence', 'desc': 'SESSİZLİK YEMİNİ: Bu tur konuşmak yasak!'},
            {'id': 'double_trouble', 'desc': 'ÇİFTE BELA: Bugün iki kişi asılacak!'}
        ]
        chaos_event = random.choice(chaos_events)
        room['chaos_event'] = chaos_event
    else:
        room['chaos_event'] = None

    emit('state_update', {
        'state': 'day', 
        'message': f'Gündüz vakti! Tartışma süresi: {duration} saniye.',
        'duration': duration,
        'chaos_event': chaos_event
    }, to=room_code)
    
    # Vampirlere takım arkadaşlarını bildir
    vampire_team = [p['name'] for p in room['players'].values() if p['role'] in ['vampire', 'traitor']]
    for pid, p in room['players'].items():
        if p['role'] in ['vampire', 'traitor']:
            emit('vampire_team', {'teammates': vampire_team}, room=pid)

    # Arka planda sayacı başlat
    socketio.start_background_task(run_timer, room_code, duration)

def run_timer(room_code, duration):
    """Basit bir geri sayım ve ardından oylamaya geçiş"""
    import time
    time.sleep(duration)
    
    # Eğer oyun hala devam ediyorsa oylamaya geç
    room = rooms.get(room_code)
    if room and room['game_state'] == 'day':
        with app.app_context():
            start_voting_phase(room_code)

def start_voting_phase(room_code):
    room = rooms.get(room_code)
    if not room: return
    
    room['game_state'] = 'voting'
    # Oyları sıfırla
    for p in room['players'].values():
        p['voted_for'] = None

    emit('state_update', {
        'state': 'voting', 
        'message': 'Oylama Başladı! Şüphelendiğin kişiye oy ver.'
    }, to=room_code)
    
    # Oy verilebilir yaşayan oyuncuların listesini gönder
    alive_players = {sid: p['name'] for sid, p in room['players'].items() if p['is_alive']}
    emit('voting_started', {'candidates': alive_players}, to=room_code)

@socketio.on('vote')
def handle_vote(data):
    room_code = data.get('room_code')
    target_id = data.get('target_id') # Oy verilen kişinin SID'si veya adı (SID daha güvenli)
    
    room = rooms.get(room_code)
    if not room or room['game_state'] != 'voting':
        return
        
    voter_id = request.sid
    if not room['players'][voter_id]['is_alive']:
        return # Ölüler oy kullanamaz

    room['players'][voter_id]['voted_for'] = target_id
    
    # Herkesin oy kullanıp kullanmadığını kontrol et
    alive_count = len([p for p in room['players'].values() if p['is_alive']])
    votes_cast = len([p for p in room['players'].values() if p['is_alive'] and p['voted_for'] is not None])
    
    emit('vote_update', {'votes_cast': votes_cast, 'total_alive': alive_count}, to=room_code)
    
    if votes_cast >= alive_count:
        evaluate_votes(room_code)

def evaluate_votes(room_code):
    room = rooms.get(room_code)
    
    # Oyları say
    vote_counts = {}
    for p in room['players'].values():
        if p['is_alive'] and p['voted_for']:
            target = p['voted_for']
            vote_counts[target] = vote_counts.get(target, 0) + 1
            
    if not vote_counts:
        emit('game_over', {'message': 'Kimse oy kullanmadı. Oyun bitti (veya berabere).'}, to=room_code)
        return

    # En çok oy alanı bul
    max_votes = max(vote_counts.values())
    candidates = [target for target, count in vote_counts.items() if count == max_votes]
    
    if len(candidates) > 1:
        # Beraberlik durumu - Şimdilik kimse ölmesin veya rastgele? 
        # Basitlik için kimse ölmesin diyelim
        emit('vote_result', {'message': 'Oylar eşit! Kimse asılmadı.', 'victim_name': None}, to=room_code)
        # Yeni gün başlat veya geceye geç? Basitlik için yeni tur (Game Loop döngüsü henüz tam değil)
        # Oyun bitip bitmediğini kontrol etmemiz lazım ama şimdilik döngü yok.
    else:
        victim_sid = candidates[0]
        victim_name = room['players'][victim_sid]['name']
        room['players'][victim_sid]['is_alive'] = False
        victim_role = room['players'][victim_sid]['role']
        
        emit('vote_result', {
            'message': f'{victim_name} asıldı! Rolü: {victim_role}', 
            'victim_name': victim_name,
            'victim_role': victim_role,
            'victim_id': victim_sid
        }, to=room_code)
        
        if room.get('chaos_event', {}).get('id') == 'double_trouble':
             # İkinci bir oylama yapılmalı mı? Basitlik için sadece win check.
             pass
             
        check_win_condition(room_code)
        
        # Oyun bitmediyse Geceye Geç
        if room['game_state'] != 'game_over':
            socketio.sleep(3)
            start_night_phase(room_code)

def check_win_condition(room_code):
    room = rooms.get(room_code)
    alive_vampires = len([p for p in room['players'].values() if p['is_alive'] and p['role'] == 'vampire'])
    alive_villagers = len([p for p in room['players'].values() if p['is_alive'] and p['role'] == 'villager'])
    
    if alive_vampires == 0:
        emit('game_end', {'winner': 'villagers', 'message': 'Tüm vampirler öldü! Köylüler kazandı!'}, to=room_code)
    elif alive_vampires >= alive_villagers:
        emit('game_end', {'winner': 'vampires', 'message': 'Vampirler köylüleri ele geçirdi! Vampirler kazandı!'}, to=room_code)
    else:
        # Oyun devam ediyor
        pass

def start_night_phase(room_code):
    room = rooms.get(room_code)
    if not room: return
    
    room['game_state'] = 'night'
    room['night_actions'] = {} # Aksiyonları temizle
    
    alive_players_map = {sid: p['name'] for sid, p in room['players'].items() if p['is_alive']}
    
    emit('night_started', {
        'message': 'Gece çöktü... Vampirler avlanıyor, Doktor ve Medyum görev başına!',
        'alive_players': alive_players_map
    }, to=room_code)
    
    # Gece süresi (Sabit 30sn)
    socketio.start_background_task(run_night_timer, room_code, 30)

def run_night_timer(room_code, duration):
    import time
    time.sleep(duration)
    
    room = rooms.get(room_code)
    if room and room['game_state'] == 'night':
        with app.app_context():
            resolve_night(room_code)

@socketio.on('night_action')
def handle_night_action(data):
    room_code = data.get('room_code')
    action = data.get('action') # kill, protect, inspect
    target_id = data.get('target_id')
    sender_id = request.sid
    
    room = rooms.get(room_code)
    if not room or room['game_state'] != 'night': return
    
    # Role uygunluk kontrolü (Basitçe güveniyorum, server-side rol kontrolü eklenebilir)
    # Kaydet
    room['night_actions'][sender_id] = {'action': action, 'target': target_id}
    
    # Medyum anında cevap almalı
    if action == 'inspect':
        target_role = room['players'].get(target_id, {}).get('role', 'unknown')
        role_display = 'VAMPİR' if target_role == 'vampire' else 'TEMİZ'
        emit('night_result', {'message': f'Medyum Sezisi: Hedef {role_display}!'}, room=sender_id)

def resolve_night(room_code):
    room = rooms.get(room_code)
    actions = room.get('night_actions', {})
    
    kills = []
    protects = []
    
    # Aksiyonları topla
    for actor_id, act in actions.items():
        if act['action'] == 'kill':
            kills.append(act['target'])
        elif act['action'] == 'protect':
            protects.append(act['target'])
            
    # Sonuçları işle
    dead_players = []
    
    # Vampirler ortak karar vermeli ama burada son vuran geçerli olsun (Basitlik)
    # Veya kills listesindeki en çok geçen isim.
    if kills:
        target_to_kill = max(set(kills), key=kills.count)
        
        if target_to_kill in protects:
            message = "Gece sessiz geçti. Doktor bir hayat kurtardı!"
        else:
            # Enfeksiyon Modu kontrolü?
            # Şimdilik direkt ölüm
            room['players'][target_to_kill]['is_alive'] = False
            victim_name = room['players'][target_to_kill]['name']
            dead_players.append(victim_name)
            message = f"Gece korkunç geçti! {victim_name} ölü bulundu."
    else:
        message = "Gece olaysız geçti."
        
    emit('night_result', {'message': message}, to=room_code)
    
    check_win_condition(room_code)
    if room['game_state'] != 'game_over':
        socketio.sleep(4)
        start_day_phase(room_code)

# --- Ekstra Özellikler Handler ---

@socketio.on('chaos_note')
def handle_chaos_note(data):
    # Rastgele birine mesaj gider
    room_code = data['room_code']
    message = data['message']
    room = rooms.get(room_code)
    
    if room:
        alive_sids = [sid for sid, p in room['players'].items() if p['is_alive'] and sid != request.sid]
        if alive_sids:
            target = random.choice(alive_sids)
            emit('notification', {'title': 'Karanlık Fısıltı', 'message': message, 'type': 'chaos'}, room=target)

@socketio.on('haunt_action')
def handle_haunt(data):
    # Ölü oyuncu herkesi korkutur
    room_code = data['room_code']
    effect = data['effect']
    emit('haunt_effect', {'effect': effect}, to=room_code)

@socketio.on('duel_click')
def handle_duel(data):
    # Düello mantığı (Basit: İlk tıklayan kazanır gibi veya sayaç)
    # Şimdilik sadece log
    pass

@socketio.on('chat_message')
def handle_chat(data):
    """Oyun içi sohbet mesajı"""
    room_code = data.get('room_code')
    message = data.get('message', '').strip()
    
    if not message or not room_code:
        return
        
    room = rooms.get(room_code)
    if not room or request.sid not in room['players']:
        return
    
    sender_name = room['players'][request.sid]['name']
    is_alive = room['players'][request.sid]['is_alive']
    
    # Ölüler sadece diğer ölülere mesaj atabilir (isteğe bağlı kural)
    # Şimdilik herkes herkese atsın
    
    emit('new_chat_message', {
        'sender': sender_name,
        'message': message,
        'timestamp': time.strftime('%H:%M'),
        'is_ghost': not is_alive
    }, to=room_code)

@socketio.on('leave_lobby')
def handle_leave_lobby(data):
    """Lobiden ayrılma"""
    room_code = data.get('room_code')
    room = rooms.get(room_code)
    
    if room and request.sid in room['players']:
        del room['players'][request.sid]
        leave_room(room_code)
        join_room('global_lobby')
        
        # Oda boşaldıysa sil
        if len(room['players']) == 0:
            del rooms[room_code]
        else:
            emit('player_list_update', {'players': room['players']}, to=room_code)
        
        socketio.emit('room_list_update', {'rooms': get_public_rooms()}, to='global_lobby')


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000, host='0.0.0.0')
