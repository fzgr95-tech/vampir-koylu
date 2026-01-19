const socket = io();

// Durum yönetimi
let currentRoom = null;
let myUsername = null;
let isAdmin = false;
let myRole = null;
let isAlive = true;

// DOM Elementleri
const screens = {
    home: document.getElementById('screen-home'),
    lobby: document.getElementById('screen-lobby'),
    game: document.getElementById('screen-game')
};

const forms = {
    create: document.getElementById('create-room-form')
};

const modal = document.getElementById('password-modal');
const duelOverlay = document.getElementById('duel-overlay');

// Ekran Geçişleri
function showScreen(screenName) {
    Object.values(screens).forEach(screen => screen.classList.remove('active'));
    screens[screenName].classList.add('active');
}

function showCreateRoom() {
    forms.create.classList.remove('hidden');
    document.querySelector('.room-list-container').classList.add('hidden');
    document.querySelector('.menu-buttons').classList.add('hidden');
}

function showHome() {
    forms.create.classList.add('hidden');
    document.querySelector('.room-list-container').classList.remove('hidden');
    document.querySelector('.menu-buttons').classList.remove('hidden');
    showScreen('home');
}

// Modal Logic
let selectedRoomCode = null;

function openPasswordModal(roomCode) {
    selectedRoomCode = roomCode;
    modal.classList.remove('hidden');
    document.getElementById('join-password-input').value = '';
    document.getElementById('join-password-input').focus();
}

function closePasswordModal() {
    modal.classList.add('hidden');
    selectedRoomCode = null;
}

document.getElementById('confirm-join-btn').addEventListener('click', () => {
    const password = document.getElementById('join-password-input').value;
    attemptJoin(selectedRoomCode, password);
    closePasswordModal();
});

// Socket Emit İşlemleri
function createRoom() {
    const username = document.getElementById('global-username').value;
    if (!username) {
        showToast("Lütfen önce bir kullanıcı adı gir!", "error");
        return;
    }
    myUsername = username;

    const roomName = document.getElementById('create-room-name').value;
    const password = document.getElementById('create-password').value;
    const vampireCount = document.getElementById('vampire-count').value;
    const duration = document.getElementById('speak-duration').value;
    const infectionMode = document.getElementById('enable-infection').checked;

    socket.emit('create_room', {
        room_name: roomName,
        password: password,
        vampire_count: vampireCount,
        duration: duration,
        infection_mode: infectionMode
    });
}

function attemptJoin(roomCode, password = '') {
    const username = document.getElementById('global-username').value;
    if (!username) {
        showToast("Lütfen önce bir kullanıcı adı gir!", "error");
        return;
    }
    myUsername = username;

    socket.emit('join_room', {
        room_code: roomCode,
        password: password,
        username: username
    });
}

function startGame() {
    if (!isAdmin) return;
    socket.emit('start_game', { room_code: currentRoom });
}

function castVote(targetId) {
    socket.emit('vote', {
        room_code: currentRoom,
        target_id: targetId
    });

    document.querySelectorAll('.vote-btn').forEach(btn => btn.disabled = true);
    showToast("Oy kullanıldı!", "success");
}

function performNightAction(action, targetId) {
    socket.emit('night_action', {
        room_code: currentRoom,
        action: action,
        target_id: targetId
    });

    document.getElementById('night-controls').classList.add('hidden');
    showToast("Gece hamlesi yapıldı...", "info");
}

function haunt(effect) {
    // Ölü oyuncu herkesi veya rastgele hedefi korkutuyor
    // Basit olsun: tüm canlılara gönderelim veya lobby'den birini seçelim.
    // Şimdilik sadece efekt gönderiyorum, server halletsin rastgele.
    // Veya basitçe: "Tüm odaya gönder"
    socket.emit('haunt_action', {
        room_code: currentRoom,
        target_id: currentRoom, // Room broadcast logic needs server tweak or explicit target loop. 
        // Let's assume server broadcasts to room for now or we pick a random alive player client side? No, server side better.
        // For 'haunt', let's implemented simpler: client asks server to haunt someone.
        // Currently Server implementation: emits 'haunt_effect' to specific target_id.
        // As a dead user, I don't see buttons to pick target yet, so making it 'Random Haunt' for now.
        effect: effect
    });
    showToast("Musallat olundu! 👻");
}

function sendChaosNote() {
    const msg = document.getElementById('chaos-msg-input').value;
    if (!msg) return;

    socket.emit('chaos_note', {
        room_code: currentRoom,
        message: msg
    });
    document.getElementById('chaos-msg-input').value = '';
    showToast("Fısıltı rüzgara karıştı...", "success");
}

// --- Sohbet Fonksiyonları ---
function sendChatMessage() {
    const input = document.getElementById('chat-input');
    if (!input) return;
    const message = input.value.trim();
    if (!message) return;

    socket.emit('chat_message', {
        room_code: currentRoom,
        message: message
    });
    input.value = '';
}

function sendLobbyChatMessage() {
    const input = document.getElementById('lobby-chat-input');
    if (!input) return;
    const message = input.value.trim();
    if (!message) return;

    socket.emit('chat_message', {
        room_code: currentRoom,
        message: message
    });
    input.value = '';
}

// --- Geri Sayım ---
let countdownInterval = null;

function startCountdown(seconds) {
    const display = document.getElementById('countdown-display');
    const timer = document.getElementById('countdown-timer');

    if (!display || !timer) return;

    // Önceki sayacı temizle
    if (countdownInterval) clearInterval(countdownInterval);

    display.classList.remove('hidden');
    let remaining = seconds;
    timer.innerText = remaining;
    timer.classList.remove('countdown-urgent');

    countdownInterval = setInterval(() => {
        remaining--;
        timer.innerText = remaining;

        if (remaining <= 10) {
            timer.classList.add('countdown-urgent');
        }

        if (remaining <= 0) {
            clearInterval(countdownInterval);
            display.classList.add('hidden');
        }
    }, 1000);
}

function stopCountdown() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    const display = document.getElementById('countdown-display');
    if (display) display.classList.add('hidden');
}

// --- Lobiden Çıkış ---
function leaveLobby() {
    socket.emit('leave_lobby', { room_code: currentRoom });
    currentRoom = null;
    isAdmin = false;
    showHome();
}

// --- Listeners ---

socket.on('room_list_update', (data) => {
    const list = document.getElementById('room-list');
    if (!list) return;
    list.innerHTML = '';

    if (data.rooms.length === 0) {
        list.innerHTML = '<div class="empty-list">Hiç oda yok...</div>';
        return;
    }

    data.rooms.forEach(room => {
        const div = document.createElement('div');
        div.className = 'room-item';
        div.onclick = () => {
            if (room.has_password) {
                openPasswordModal(room.code);
            } else {
                attemptJoin(room.code);
            }
        };

        div.innerHTML = `
            <div class="room-info">
                <h4>${room.name}</h4>
                <p>${room.player_count} Oyuncu • ${room.status}</p>
            </div>
            ${room.has_password ? '<div class="room-lock">🔒</div>' : ''}
        `;
        list.appendChild(div);
    });
});

socket.on('room_created', (data) => {
    currentRoom = data.room_code;
    const password = document.getElementById('create-password').value;
    socket.emit('join_room', {
        room_code: currentRoom,
        password: password,
        username: myUsername
    });
});

socket.on('joined_room', (data) => {
    currentRoom = data.room_code;
    isAdmin = data.is_admin;
    isAlive = true;

    const lobbyNameDisplay = document.getElementById('lobby-name-display');
    if (lobbyNameDisplay) lobbyNameDisplay.innerText = data.room_name;
    document.getElementById('lobby-code-display').innerText = currentRoom;

    if (isAdmin) {
        document.getElementById('admin-controls').classList.remove('hidden');
    } else {
        document.getElementById('admin-controls').classList.add('hidden');
    }

    showScreen('lobby');
});

socket.on('player_list_update', (data) => {
    const playersList = document.getElementById('lobby-players-list');
    playersList.innerHTML = '';

    Object.values(data.players).forEach(player => {
        const div = document.createElement('div');
        div.className = 'player-card';
        div.innerHTML = `
            <div class="player-avatar">${player.name[0].toUpperCase()}</div>
            <div class="player-name">${player.name}</div>
            ${player.is_admin ? '<small>(Admin)</small>' : ''}
        `;
        playersList.appendChild(div);
    });
});

socket.on('game_started', (data) => {
    myRole = data.role;
    showScreen('game');

    const badge = document.getElementById('my-role-badge');
    badge.innerText = data.role_name.toUpperCase();
    badge.className = `role-badge role-${myRole}`; // role-vampire, role-doctor etc.

    showToast(`Oyun Başladı! Rolün: ${data.role_name}`);

    if (data.teammates && data.teammates.length > 0) {
        showToast(`Takım Arkadaşların: ${data.teammates.join(', ')}`);
    }

    // UI Cleanup
    document.getElementById('game-players-grid').innerHTML = '';
    document.getElementById('voting-controls').classList.add('hidden');
    document.getElementById('night-controls').classList.add('hidden');
    document.getElementById('dead-controls').classList.add('hidden');
    document.body.classList.remove('night-mode');
});

// Chaos & Day State
socket.on('state_update', (data) => {
    const phaseDisplay = document.getElementById('game-phase');

    // Mesajı göster
    phaseDisplay.innerText = data.message;
    document.body.classList.remove('night-mode');

    // 5 saniye sonra sadece faz ismini göster
    if (data.state === 'day') {
        setTimeout(() => {
            phaseDisplay.innerText = '☀️ GÜNDÜZ';
        }, 5000);
    } else if (data.state === 'voting') {
        phaseDisplay.innerText = '🗳️ OYLAMA';
    }

    // Geri sayımı başlat
    if (data.duration) {
        startCountdown(data.duration);
    }

    if (data.chaos_event) {
        const chaos = document.getElementById('chaos-notification');
        const chaosDesc = document.getElementById('chaos-desc');
        if (chaos && chaosDesc) {
            chaosDesc.innerText = data.chaos_event.desc;
            chaos.classList.remove('hidden');
            setTimeout(() => chaos.classList.add('hidden'), 5000);
        }

        // Handle Chaos Effects
        if (data.chaos_event.id === 'blind_vote') showToast("Bu tur oylar GİZLİ!", "warning");
    }

    // Fake Stress Analysis Trigger (Randomly)
    if (Math.random() > 0.7) {
        setTimeout(() => {
            const overlay = document.getElementById('stress-overlay');
            if (overlay) {
                overlay.classList.remove('hidden');
                setTimeout(() => overlay.classList.add('hidden'), 3000);
            }
        }, Math.random() * 10000);
    }
});

// Voting
socket.on('voting_started', (data) => {
    // Geri sayımı durdur
    stopCountdown();

    // Faz göstergesini güncelle
    document.getElementById('game-phase').innerText = '🗳️ OYLAMA';

    const votingPanel = document.getElementById('voting-controls');
    votingPanel.classList.remove('hidden');

    const grid = document.getElementById('game-players-grid');
    grid.innerHTML = '';

    Object.entries(data.candidates).forEach(([sid, name]) => {
        const div = document.createElement('div');
        div.className = 'game-player-card';
        // Kendi kendine oy verme engeli? Genelde serbesttir ama mantıken başkasına verirsin.
        const canVote = isAlive;

        div.innerHTML = `
             <div class="player-avatar">${name[0]}</div>
             <div class="player-name">${name}</div>
             <button class="btn btn-secondary vote-btn" 
                onclick="castVote('${sid}')" 
                ${!canVote ? 'disabled' : ''}>OYLA</button>
        `;
        grid.appendChild(div);
    });
});

socket.on('vote_result', (data) => {
    showToast(data.message, data.victim_name ? "error" : "info");
    document.getElementById('voting-controls').classList.add('hidden');

    if (data.victim_name && data.victim_name === myUsername) {
        isAlive = false;
        document.getElementById('dead-controls').classList.remove('hidden');
        showToast("Öldün... Ama intikam alabilirsin!", "error");
    }
});

// Duel
socket.on('duel_started', (data) => {
    duelOverlay.classList.remove('hidden');
    // Simple click listener on button
    const btn = document.getElementById('duel-click-btn');
    btn.onclick = () => {
        socket.emit('duel_click', { room_code: currentRoom });
        // Visual feedback
        btn.style.transform = 'scale(0.9)';
        setTimeout(() => btn.style.transform = 'scale(1)', 50);
    };

    // Hide after 6 seconds (server logic is 6s)
    setTimeout(() => {
        duelOverlay.classList.add('hidden');
    }, 6000);
});

// Night Phase
socket.on('night_started', (data) => {
    document.body.classList.add('night-mode');
    showToast(data.message, "warning");
    document.getElementById('game-phase').innerText = "GECE";

    // Show Action Panel based on Role
    if (!isAlive) return;

    const nightPanel = document.getElementById('night-controls');
    const nightTitle = document.getElementById('night-action-title');
    const nightDesc = document.getElementById('night-action-desc');
    const targetsDiv = document.getElementById('night-targets');
    targetsDiv.innerHTML = '';

    let action = null;

    if (myRole === 'vampire') {
        action = 'kill';
        nightTitle.innerText = "AV ZAMANI";
        nightDesc.innerText = "Kimi öldüreceksin?";
    } else if (myRole === 'doctor') {
        action = 'protect';
        nightTitle.innerText = "İLKYARDIM";
        nightDesc.innerText = "Kimi koruyacaksın?";
    } else if (myRole === 'seer') {
        action = 'inspect';
        nightTitle.innerText = "KEHANET";
        nightDesc.innerText = "Kimi sorgulayacaksın?";
    }

    if (action && data.alive_players) {
        nightPanel.classList.remove('hidden');

        Object.entries(data.alive_players).forEach(([sid, name]) => {
            // Self-protect allowed? Usually yes for doctor.
            // Vampires shouldn't kill each other usually, but game allows.
            // Simplified: Show all alive players.

            const btn = document.createElement('button');
            btn.className = 'btn btn-secondary'; // Changed to secondary for better visibility in night
            btn.style.margin = '5px';
            btn.innerText = name;
            btn.onclick = () => performNightAction(action, sid);
            targetsDiv.appendChild(btn);
        });
    } else if (action) {
        // Fallback if no list provided (should not happen with updated backend)
        nightPanel.classList.remove('hidden');
        nightDesc.innerText = "Hedef listesi yüklenemedi...";
    }
});

socket.on('night_result', (data) => {
    document.body.classList.remove('night-mode');
    alert(data.message); // Show summary
    document.getElementById('night-controls').classList.add('hidden');
});

socket.on('haunt_effect', (data) => {
    if (data.effect === 'vibrate') {
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
        document.body.classList.add('shake');
        setTimeout(() => document.body.classList.remove('shake'), 500);
    } else if (data.effect === 'jumpscare') {
        // Simple screen flash
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.background = 'white';
        overlay.style.zIndex = '10000';
        document.body.appendChild(overlay);
        setTimeout(() => overlay.remove(), 100);
    }
});

socket.on('notification', (data) => {
    showToast(`${data.title}: ${data.message}`, "chaos");
});

// Sohbet Mesajı
socket.on('new_chat_message', (data) => {
    // Mesaj HTML'i oluştur
    const msgHTML = `
        <span class="chat-time">${data.timestamp}</span>
        <strong class="chat-sender">${data.sender}${data.is_ghost ? ' 👻' : ''}:</strong> 
        <span class="chat-text">${data.message}</span>
    `;

    // Oyun sohbetine ekle
    const gameMessages = document.getElementById('chat-messages');
    if (gameMessages) {
        const msg = document.createElement('div');
        msg.className = 'chat-message' + (data.is_ghost ? ' ghost-message' : '');
        msg.innerHTML = msgHTML;
        gameMessages.appendChild(msg);
        gameMessages.scrollTop = gameMessages.scrollHeight;
    }

    // Lobi sohbetine ekle
    const lobbyMessages = document.getElementById('lobby-chat-messages');
    if (lobbyMessages) {
        const msg = document.createElement('div');
        msg.className = 'chat-message' + (data.is_ghost ? ' ghost-message' : '');
        msg.innerHTML = msgHTML;
        lobbyMessages.appendChild(msg);
        lobbyMessages.scrollTop = lobbyMessages.scrollHeight;
    }
});

// Hata Mesajları
socket.on('error', (data) => {
    showToast(data.message, "error");
});

// Oyun Sonu
socket.on('game_end', (data) => {
    stopCountdown();
    showToast(data.message, data.winner === 'vampires' ? "error" : "success");

    // Lobiye dön butonu göster veya otomatik dön
    setTimeout(() => {
        if (confirm('Oyun bitti! Ana menüye dönmek ister misin?')) {
            leaveLobby();
        }
    }, 3000);
});

// Helper
function showToast(message, type = "info") {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
