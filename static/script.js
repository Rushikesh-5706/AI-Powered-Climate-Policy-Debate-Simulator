function setSuggestedTopic(topic) {
    document.getElementById('topic').value = topic;
    document.getElementById('topic').focus();
}

async function startDebate() {
    const topicInput = document.getElementById('topic');
    const roundsSelect = document.getElementById('rounds');
    const startBtn = document.getElementById('start-btn');
    const statusDiv = document.getElementById('status');
    const errorBox = document.getElementById('error-box');
    const transcriptSection = document.getElementById('transcript');
    const transcriptMeta = document.getElementById('transcript-meta');
    const messagesDiv = document.getElementById('messages');

    const topic = topicInput.value.trim();
    const rounds = parseInt(roundsSelect.value, 10);

    if (!topic) {
        showError('Please enter a debate topic before running the simulation.');
        return;
    }

    // Reset UI
    startBtn.disabled = true;
    startBtn.innerHTML = '<div class="spinner"></div> Generating...';
    statusDiv.style.display = 'flex';
    errorBox.style.display = 'none';
    transcriptSection.style.display = 'none';
    messagesDiv.innerHTML = '';

    try {
        const response = await fetch('/debate/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: topic, rounds: rounds }),
        });

        if (!response.ok) {
            let detail = 'The simulation could not be completed.';
            try {
                const errData = await response.json();
                detail = errData.detail || detail;
            } catch (_) {}
            throw new Error(detail);
        }

        const data = await response.json();
        renderTranscript(data.messages, topic, rounds);

        statusDiv.style.display = 'none';
        transcriptSection.style.display = 'block';
    } catch (err) {
        statusDiv.style.display = 'none';
        showError(err.message);
    } finally {
        startBtn.disabled = false;
        startBtn.innerHTML = '<span class="btn-icon">⚡</span> Run Simulation';
    }
}

function renderTranscript(messages, topic, rounds) {
    const transcriptMeta = document.getElementById('transcript-meta');
    const messagesDiv = document.getElementById('messages');

    transcriptMeta.innerHTML =
        '<div class="meta-item"><span class="meta-label">Topic</span><span class="meta-value">' + escapeHtml(topic) + '</span></div>' +
        '<div class="meta-item"><span class="meta-label">Rounds</span><span class="meta-value">' + rounds + '</span></div>' +
        '<div class="meta-item"><span class="meta-label">Statements</span><span class="meta-value">' + messages.length + '</span></div>';

    const agentEmoji = { USA: '🇺🇸', EU: '🇪🇺', China: '🇨🇳' };
    const agentAvatarClass = { USA: 'avatar-usa', EU: 'avatar-eu', China: 'avatar-china' };

    let currentRound = 0;

    messages.forEach(function (msg, idx) {
        if (msg.round !== currentRound) {
            currentRound = msg.round;
            const divider = document.createElement('div');
            divider.className = 'round-divider';
            divider.innerHTML =
                '<div class="round-divider-line"></div>' +
                '<div class="round-divider-label">Round ' + currentRound + '</div>' +
                '<div class="round-divider-line"></div>';
            messagesDiv.appendChild(divider);
        }

        const card = document.createElement('div');
        const agentKey = msg.agent;
        const agentClass = 'agent-' + agentKey.toLowerCase();
        const stanceClass = 'stance-' + msg.stance;
        const avatarClass = agentAvatarClass[agentKey] || 'avatar-usa';
        const emoji = agentEmoji[agentKey] || '🌍';

        card.className = 'message-card ' + agentClass;
        card.style.animationDelay = (idx * 0.04) + 's';

        const ts = new Date(msg.timestamp).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });

        card.innerHTML =
            '<div class="message-header">' +
                '<div class="agent-avatar ' + avatarClass + '">' + emoji + '</div>' +
                '<span class="agent-name">' + escapeHtml(msg.agent) + '</span>' +
                '<span class="round-badge">Round ' + msg.round + '</span>' +
                '<span class="stance-badge ' + stanceClass + '">' + escapeHtml(msg.stance) + '</span>' +
                '<span class="timestamp">' + ts + '</span>' +
            '</div>' +
            '<div class="message-body">' + escapeHtml(msg.message) + '</div>';

        messagesDiv.appendChild(card);
    });
}

function showError(message) {
    const errorBox = document.getElementById('error-box');
    errorBox.textContent = '⚠ ' + message;
    errorBox.style.display = 'block';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(text)));
    return div.innerHTML;
}
