<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة المقرأة - استفسارات وتسميع</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        /* --- الأنماط العامة --- */
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 15px; background: #f4f7fa; }
        .container { max-width: 700px; margin: auto; }
        .card { background: white; border-radius: 12px; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); border-right: 5px solid #f39c12; }
        .card.tashmi-card { border-right-color: #9b59b6; }
        .card.answered { border-right-color: #27ae60; }
        .card.processing { border-right-color: #3498db; opacity: 0.9; }
        h1 { color: #2c3e50; font-size: 22px; margin: 0; }
        .user { font-weight: bold; color: #2980b9; }
        .user a { color: #2980b9; text-decoration: none; }
        .user a:hover { text-decoration: underline; }
        .question { margin: 10px 0; background: #ecf0f1; padding: 10px; border-radius: 8px; }
        .reply-area { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; margin: 5px 0; font-family: inherit; }
        .reply-area:disabled { background: #ecf0f1; color: #7f8c8d; cursor: not-allowed; }
        .send-btn { background: #0088cc; color: white; border: none; padding: 10px 20px; border-radius: 8px; width: 100%; font-size: 16px; cursor: pointer; margin-top: 5px; }
        .send-btn:disabled { background: #95a5a6; cursor: not-allowed; }
        .assign-btn { background: #f39c12; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }
        .assign-btn:disabled { background: #95a5a6; cursor: not-allowed; }
        .unassign-btn { background: #e67e22; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; }
        .unassign-btn:disabled { background: #95a5a6; cursor: not-allowed; }
        .pending-badge { background: #f39c12; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; display: inline-block; }
        .answered-badge { background: #27ae60; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; display: inline-block; }
        .processing-badge { background: #3498db; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; display: inline-block; }
        .tashmi-badge { background: #9b59b6; color: white; padding: 2px 10px; border-radius: 20px; font-size: 12px; display: inline-block; }
        .reply-text { background: #d5f5e3; padding: 10px; border-radius: 8px; color: #1e8449; margin-top: 10px; }
        .processing-text { background: #d6eaf8; padding: 10px; border-radius: 8px; color: #1a5276; margin-top: 10px; text-align: center; }
        .loader { text-align: center; color: #7f8c8d; padding: 20px; }
        .error { color: red; text-align: center; }
        .actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 5px 0; }

        /* --- تبويبات التنقل --- */
        .tabs { display: flex; gap: 5px; margin-bottom: 20px; background: #ecf0f1; border-radius: 12px; padding: 5px; }
        .tab-btn { flex: 1; padding: 10px; border: none; border-radius: 10px; font-size: 16px; font-weight: bold; cursor: pointer; background: transparent; color: #7f8c8d; transition: 0.3s; }
        .tab-btn.active { background: white; color: #2c3e50; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .tab-btn:hover { background: rgba(255,255,255,0.5); }

        /* --- شريط المجموعات (Tashmi) --- */
        .groups-scroll {
            display: flex;
            align-items: center;
            gap: 8px;
            overflow-x: auto;
            padding: 5px 0 15px 0;
            white-space: nowrap;
            scrollbar-width: thin;
            border-bottom: 1px solid #eee;
            margin-bottom: 15px;
            flex-wrap: nowrap;
        }
        .group-tab {
            flex: 0 0 auto;
            background: #ecf0f1;
            color: #2c3e50;
            border: none;
            padding: 8px 18px;
            border-radius: 30px;
            font-size: 14px;
            cursor: pointer;
            transition: 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
            font-weight: 500;
        }
        .group-tab.active {
            background: #2c3e50;
            color: white;
            box-shadow: 0 2px 8px rgba(44,62,80,0.3);
        }
        .group-tab .badge {
            background: #e74c3c;
            color: white;
            padding: 0 8px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
        }
        .group-tab.active .badge { background: rgba(255,255,255,0.3); color: white; }
        .group-tab .badge.zero { background: #bdc3c7; color: #7f8c8d; }

        /* --- مشغل الصوت مع أزرار السرعة --- */
        .audio-player-wrapper { margin: 10px 0; background: #f8f9fa; padding: 12px; border-radius: 10px; }
        .audio-player-wrapper audio { width: 100%; outline: none; }
        .speed-btns { display: flex; gap: 5px; margin-top: 8px; flex-wrap: wrap; }
        .speed-btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 4px 14px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 13px;
            font-weight: bold;
            transition: 0.2s;
        }
        .speed-btn:hover { background: #2980b9; transform: scale(1.05); }
        .speed-btn.active-speed { background: #e67e22; box-shadow: 0 2px 6px rgba(230,126,34,0.4); }

        /* --- النوافذ المنبثقة والإحصائيات --- */
        .header-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 10px; }
        .header-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .refresh-btn { background: #2ecc71; color: white; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .refresh-btn:disabled { background: #95a5a6; }
        .delete-btn { background: #e74c3c; color: white; border: none; padding: 8px 15px; border-radius: 8px; cursor: pointer; font-size: 14px; }
        .delete-btn:disabled { background: #95a5a6; }
        .stats-bar { background: #ecf0f1; border-radius: 10px; padding: 10px 15px; margin-bottom: 15px; display: flex; justify-content: space-around; text-align: center; font-size: 14px; flex-wrap: wrap; gap: 5px; }
        .stats-bar span { font-weight: bold; }
        .stats-pending { color: #f39c12; }
        .stats-processing { color: #3498db; }
        .stats-answered { color: #27ae60; }
        .stats-total { color: #2980b9; }
        .stats-tashmi-pending { color: #9b59b6; }
    </style>
</head>
<body>
<div class="container">
    <div class="header-actions">
        <div class="header-left"><h1>📋 لوحة المقرأة</h1></div>
        <div class="header-right">
            <button class="refresh-btn" id="refreshBtn" onclick="loadCurrentTab()">🔄 تحديث</button>
            <button class="delete-btn" id="deleteBtn" onclick="deleteAnswered()">🗑️ حذف الأسئلة التي تم الرد عليها</button>
        </div>
    </div>

    <!-- تبويبات التنقل -->
    <div class="tabs">
        <button class="tab-btn active" id="tabAsk" onclick="switchTab('ask')">📩 الاستفسارات</button>
        <button class="tab-btn" id="tabTashmi" onclick="switchTab('tashmi')">🎙️ التسميع</button>
    </div>

    <!-- ===== تبويب الاستفسارات ===== -->
    <div id="ask-tab">
        <div class="stats-bar">
            <div>⏳ في الانتظار: <span class="stats-pending" id="pendingCount">0</span></div>
            <div>🔄 قيد المعالجة: <span class="stats-processing" id="processingCount">0</span></div>
            <div>✅ تم الرد: <span class="stats-answered" id="answeredCount">0</span></div>
            <div>📊 المجموع: <span class="stats-total" id="totalCount">0</span></div>
        </div>
        <div id="questions-container"><div class="loader">⏳ جاري التحميل...</div></div>
    </div>

    <!-- ===== تبويب التسميع ===== -->
    <div id="tashmi-tab" style="display: none;">
        <!-- شريط المجموعات -->
        <div class="groups-scroll" id="groupsContainer">
            <!-- سيتم توليد الأزرار بواسطة JavaScript -->
        </div>
        <div class="stats-bar">
            <div>⏳ معلق: <span class="stats-tashmi-pending" id="tashmiPendingCount">0</span></div>
            <div>📊 المجموع: <span class="stats-total" id="tashmiTotalCount">0</span></div>
        </div>
        <div id="tashmi-container"><div class="loader">⏳ جاري تحميل التسميعات...</div></div>
    </div>
</div>

<script>
    const user = window.Telegram.WebApp.initDataUnsafe.user;
    const adminId = user ? user.id : null;
    const BASE_URL = "https://ask-zadbot.onrender.com"; // غيّره حسب رابط خادمك

    let currentQuestions = [];
    let currentTashmiRecords = [];
    let currentGroup = 'all';

    // ======================= دوال التبويب =======================
    function switchTab(tab) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        if (tab === 'ask') {
            document.getElementById('tabAsk').classList.add('active');
            document.getElementById('ask-tab').style.display = 'block';
            document.getElementById('tashmi-tab').style.display = 'none';
            loadQuestions();
        } else {
            document.getElementById('tabTashmi').classList.add('active');
            document.getElementById('ask-tab').style.display = 'none';
            document.getElementById('tashmi-tab').style.display = 'block';
            loadTashmiGroups();
        }
    }

    function loadCurrentTab() {
        if (document.getElementById('ask-tab').style.display !== 'none') loadQuestions();
        else loadTashmiGroups();
    }

    // ======================= دوال الاستفسارات =======================
    function formatUsername(username) {
        if (!username || username === "مجهول") return '👤 مجهول';
        return `👤 <a href="https://t.me/${username}" target="_blank">${username}</a>`;
    }

    // ========== تحميل الاستفسارات مع مهلة ==========
    async function loadQuestions() {
        const container = document.getElementById('questions-container');
        const refreshBtn = document.getElementById('refreshBtn');
        refreshBtn.disabled = true;
        container.innerHTML = '<div class="loader">⏳ جاري التحميل...</div>';
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000); // 15 ثانية مهلة
            const res = await fetch(`${BASE_URL}/get_questions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: adminId }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            if (!res.ok) throw new Error((await res.json()).error || 'فشل');
            const data = await res.json();
            currentQuestions = data;
            // تحديث الإحصائيات
            document.getElementById('pendingCount').textContent = data.filter(q => q.status === 'pending').length;
            document.getElementById('processingCount').textContent = data.filter(q => q.status === 'processing').length;
            document.getElementById('answeredCount').textContent = data.filter(q => q.status === 'answered').length;
            document.getElementById('totalCount').textContent = data.length;
            if (data.length === 0) {
                container.innerHTML = '<div class="loader" style="color:#27ae60;">✨ لا توجد استفسارات</div>';
                refreshBtn.disabled = false;
                return;
            }
            let html = '';
            for (const q of data) {
                const isAnswered = q.status === 'answered';
                const isProcessing = q.status === 'processing';
                const isAssignedToMe = isProcessing && q.assigned_to == adminId;
                const isAssignedToOther = isProcessing && !isAssignedToMe;
                let badge = '', cardClass = '', contentHtml = '';
                if (isAnswered) {
                    badge = '<span class="answered-badge">✅ تم الرد</span>';
                    cardClass = 'answered';
                    contentHtml = `<div class="reply-text"><strong>الرد:</strong> ${q.reply || ''}</div>`;
                } else if (isAssignedToOther) {
                    badge = '<span class="processing-badge">🔄 قيد المعالجة</span>';
                    cardClass = 'processing';
                    contentHtml = `<div class="processing-text">⏳ يُعالج من قبل مشرف آخر.</div>`;
                } else {
                    const isMyProcessing = isProcessing && isAssignedToMe;
                    badge = isMyProcessing ? '<span class="processing-badge">🔄 أنت تعالج</span>' : '<span class="pending-badge">⏳ في الانتظار</span>';
                    let actionsHtml = isMyProcessing ?
                        `<button class="unassign-btn" onclick="unassignQuestion(${q.id})">↩️ إلغاء التولي</button>` :
                        `<button class="assign-btn" onclick="assignQuestion(${q.id})">🔄 تولي الرد</button>`;
                    contentHtml = `
                        <div class="actions">${actionsHtml}</div>
                        <textarea class="reply-area" placeholder="اكتب ردك..." id="reply-${q.id}" ${isMyProcessing ? '' : 'disabled'}></textarea>
                        <button class="send-btn" onclick="sendReply(${q.id})" ${isMyProcessing ? '' : 'disabled'}>📤 إرسال الرد</button>
                    `;
                }
                html += `<div class="card ${cardClass}" data-id="${q.id}">${badge}<div class="user">${formatUsername(q.username)}</div><div class="question">"${q.question}"</div>${contentHtml}<div style="font-size:12px;color:#95a5a6;margin-top:5px;">📅 ${q.created_at || ''}</div></div>`;
            }
            container.innerHTML = html;
        } catch(e) {
            if (e.name === 'AbortError') {
                container.innerHTML = '<div class="error">⏱️ انتهت المهلة، حاول تحديث الصفحة</div>';
            } else {
                container.innerHTML = `<div class="error">❌ خطأ: ${e.message}</div>`;
            }
        }
        finally { refreshBtn.disabled = false; }
    }

    // ========== تحميل التسميعات مع مهلة وبدون تحميل الصوتيات فوراً ==========
    async function loadTashmiGroups() {
        const container = document.getElementById('tashmi-container');
        const refreshBtn = document.getElementById('refreshBtn');
        refreshBtn.disabled = true;
        container.innerHTML = '<div class="loader">⏳ جاري التحميل...</div>';
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);
            const res = await fetch(`${BASE_URL}/tashmi/get`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ admin_id: adminId, group: 'all' }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            if (!res.ok) throw new Error((await res.json()).error || 'فشل');
            const data = await res.json();
            currentTashmiRecords = data;
            const pendingAll = data.filter(r => r.status === 'pending').length;
            document.getElementById('tashmiPendingCount').textContent = pendingAll;
            document.getElementById('tashmiTotalCount').textContent = data.length;
            // بناء أزرار المجموعات
            const groups = new Set(data.map(r => r.group_number).filter(Boolean));
            const groupsContainer = document.getElementById('groupsContainer');
            let groupsHtml = `<button class="group-tab active" data-group="all" onclick="switchGroup('all')">📋 الكل <span class="badge ${pendingAll === 0 ? 'zero' : ''}">${pendingAll}</span></button>`;
            const sortedGroups = Array.from(groups).sort((a,b) => Number(a) - Number(b));
            sortedGroups.forEach(g => {
                const count = data.filter(r => r.group_number === g && r.status === 'pending').length;
                groupsHtml += `<button class="group-tab" data-group="${g}" onclick="switchGroup('${g}')">🎯 مجموعة ${g} <span class="badge ${count === 0 ? 'zero' : ''}">${count}</span></button>`;
            });
            groupsContainer.innerHTML = groupsHtml;
            // عرض التسميعات بدون تحميل الصوتيات (سيتم تحميلها عند الضغط على زر التشغيل)
            await renderTashmiRecordsLazy(data.filter(r => r.group_number === currentGroup || currentGroup === 'all'));
        } catch(e) {
            if (e.name === 'AbortError') {
                container.innerHTML = '<div class="error">⏱️ انتهت المهلة، حاول تحديث الصفحة</div>';
            } else {
                container.innerHTML = `<div class="error">❌ ${e.message}</div>`;
            }
        }
        finally { refreshBtn.disabled = false; }
    }

    // ========== دالة عرض التسميعات بدون تحميل الصوتيات مسبقاً ==========
    async function renderTashmiRecordsLazy(records) {
        const container = document.getElementById('tashmi-container');
        if (records.length === 0) {
            container.innerHTML = '<div class="loader" style="color:#27ae60;">🎙️ لا توجد تسميعات في هذه المجموعة</div>';
            return;
        }
        let html = '';
        for (const r of records) {
            const isAnswered = r.status === 'answered';
            const isProcessing = r.status === 'processing';
            const isAssignedToMe = isProcessing && r.assigned_to == adminId;
            const isAssignedToOther = isProcessing && !isAssignedToMe;
            let badge = '', cardClass = 'tashmi-card', contentHtml = '';

            if (isAnswered) { badge = '<span class="answered-badge">✅ تم الرد</span>'; contentHtml = `<div class="reply-text"><strong>ملاحظة المعلم:</strong> ${r.teacher_note || ''}</div>`; }
            else if (isAssignedToOther) { badge = '<span class="processing-badge">🔄 قيد المعالجة</span>'; contentHtml = `<div class="processing-text">⏳ يُعالج من قبل مشرف آخر.</div>`; }
            else {
                const isMyProcessing = isProcessing && isAssignedToMe;
                badge = isMyProcessing ? '<span class="processing-badge">🔄 أنت تعالج</span>' : '<span class="tashmi-badge">⏳ في الانتظار</span>';
                const audioId = `audio-${r.id}`;
                // لا نطلب الرابط الآن، نضعه فارغاً ونحمله عند الضغط على زر التشغيل
                const durationText = (r.duration && r.duration > 0) ? `⏱️ ${Math.floor(r.duration/60)}:${(r.duration%60).toString().padStart(2,'0')}` : '⏱️ المدة غير معروفة';
                contentHtml = `
                    <div class="audio-player-wrapper">
                        <audio controls preload="none" id="${audioId}">
                            <source src="" type="audio/mp4">
                            المتصفح لا يدعم تشغيل الصوت.
                        </audio>
                        <div style="font-size:12px;color:#7f8c8d;margin-top:4px;">${durationText}</div>
                        <button class="speed-btn" style="background:#2ecc71;color:white;border:none;padding:4px 12px;border-radius:12px;cursor:pointer;margin-top:4px;" onclick="loadAudio('${audioId}', '${r.voice_file_id}')">▶️ تحميل الصوت</button>
                        <div class="speed-btns" style="margin-top:6px;">
                            <button class="speed-btn" onclick="setSpeed('${audioId}', 1)">1x</button>
                            <button class="speed-btn" onclick="setSpeed('${audioId}', 1.5)">1.5x</button>
                            <button class="speed-btn" onclick="setSpeed('${audioId}', 2)">2x</button>
                            <button class="speed-btn" onclick="setSpeed('${audioId}', 3)">3x</button>
                            <button class="speed-btn" onclick="setSpeed('${audioId}', 4)">4x</button>
                        </div>
                    </div>
                    <div class="actions">
                        ${isMyProcessing ? `<button class="unassign-btn" onclick="unassignTashmi(${r.id})">↩️ إلغاء التولي</button>` : `<button class="assign-btn" onclick="assignTashmi(${r.id})">🔄 تولي التصحيح</button>`}
                    </div>
                    <textarea class="reply-area" placeholder="اكتب ملاحظتك على التسميع..." id="tnote-${r.id}" ${isMyProcessing ? '' : 'disabled'}></textarea>
                    <button class="send-btn" onclick="sendTashmiReply(${r.id})" ${isMyProcessing ? '' : 'disabled'}>📤 إرسال الملاحظة</button>
                `;
            }
            html += `<div class="card ${cardClass}" data-id="${r.id}">${badge}<div class="user">👤 ${formatUsername(r.username)} | <strong>المجموعة ${r.group_number}</strong></div>${contentHtml}<div style="font-size:12px;color:#95a5a6;margin-top:5px;">📅 ${r.created_at || ''}</div></div>`;
        }
        container.innerHTML = html;
    }

    // ========== دالة تحميل الصوت عند الضغط على الزر ==========
    async function loadAudio(audioId, fileId) {
        const audio = document.getElementById(audioId);
        if (!audio) return;
        const source = audio.querySelector('source');
        if (!source) return;
        // إذا كان الرابط محملاً مسبقاً، لا نعيد التحميل
        if (source.src && source.src !== '') return;
        try {
            const url = await getAudioUrl(fileId);
            source.src = url;
            audio.load(); // إعادة تحميل العنصر
            // إخفاء زر التحميل بعد نجاح التحميل
            const parent = audio.closest('.audio-player-wrapper');
            if (parent) {
                const loadBtn = parent.querySelector('button[onclick^="loadAudio"]');
                if (loadBtn) loadBtn.style.display = 'none';
            }
        } catch (e) {
            alert('❌ فشل تحميل الصوت: ' + e.message);
        }
    }

    // ========== دالة switchGroup المعدلة ==========
    async function switchGroup(groupId) {
        currentGroup = groupId;
        document.querySelectorAll('.group-tab').forEach(btn => btn.classList.remove('active'));
        const activeBtn = document.querySelector(`.group-tab[data-group="${groupId}"]`);
        if (activeBtn) activeBtn.classList.add('active');
        const filtered = currentGroup === 'all' ? currentTashmiRecords : currentTashmiRecords.filter(r => r.group_number === currentGroup);
        await renderTashmiRecordsLazy(filtered);
    }

    // ========== دالة جلب رابط الصوت ==========
    async function getAudioUrl(fileId) {
        if (!fileId) throw new Error('معرف الملف فارغ');
        const res = await fetch(`${BASE_URL}/get_audio_url`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: fileId, admin_id: adminId })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || 'فشل جلب الرابط');
        }
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        return data.url;
    }

    function setSpeed(audioId, rate) {
        const audio = document.getElementById(audioId);
        if (audio) {
            audio.playbackRate = rate;
            const parent = audio.closest('.audio-player-wrapper');
            if (parent) {
                parent.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active-speed'));
                const btns = parent.querySelectorAll('.speed-btn');
                const index = [1,1.5,2,3,4].indexOf(rate);
                if (index !== -1) btns[index].classList.add('active-speed');
            }
        }
    }

    // ========== دوال الاستفسارات ==========
    async function assignQuestion(qId) {
        try {
            const res = await fetch(`${BASE_URL}/assign`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: qId, admin_id: adminId })
            });
            const data = await res.json();
            if (!res.ok) {
                alert(`❌ فشل تولي الرد: ${data.error || 'خطأ غير معروف'}`);
                return;
            }
            loadQuestions();
        } catch(e) {
            alert(`❌ خطأ في الاتصال: ${e.message}`);
        }
    }

    async function unassignQuestion(qId) {
        try {
            const res = await fetch(`${BASE_URL}/unassign`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: qId, admin_id: adminId })
            });
            const data = await res.json();
            if (!res.ok) {
                alert(`❌ فشل إلغاء التولي: ${data.error || 'خطأ غير معروف'}`);
                return;
            }
            loadQuestions();
        } catch(e) {
            alert(`❌ خطأ في الاتصال: ${e.message}`);
        }
    }

    async function sendReply(qId) {
        const textarea = document.getElementById(`reply-${qId}`);
        const reply = textarea.value.trim();
        if (!reply) { alert('اكتب الرد'); return; }
        const btn = textarea.nextElementSibling;
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch(`${BASE_URL}/reply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: qId, reply_text: reply, admin_id: adminId })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'فشل الإرسال');
            loadQuestions();
        } catch(e) {
            alert(`❌ ${e.message}`);
            btn.disabled = false;
            btn.textContent = '📤 إرسال الرد';
        }
    }

    // ========== دوال التسميع ==========
    async function assignTashmi(recordId) {
        try {
            const res = await fetch(`${BASE_URL}/tashmi/assign`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ record_id: recordId, admin_id: adminId })
            });
            const data = await res.json();
            if (!res.ok) {
                alert(`❌ فشل تولي التصحيح: ${data.error || 'خطأ غير معروف'}`);
                return;
            }
            loadTashmiGroups();
        } catch(e) {
            alert(`❌ خطأ في الاتصال: ${e.message}`);
        }
    }

    async function unassignTashmi(recordId) {
        alert('سيتم إلغاء التولي تلقائياً بعد 15 دقيقة.');
        loadTashmiGroups();
    }

    async function sendTashmiReply(recordId) {
        const textarea = document.getElementById(`tnote-${recordId}`);
        const note = textarea.value.trim();
        if (!note) { alert('الرجاء كتابة الملاحظة'); return; }
        const btn = textarea.nextElementSibling;
        btn.disabled = true;
        btn.textContent = '⏳ جاري...';
        try {
            const res = await fetch(`${BASE_URL}/tashmi/reply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ record_id: recordId, note_text: note, admin_id: adminId })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'فشل الإرسال');
            loadTashmiGroups();
        } catch(e) {
            alert(`❌ ${e.message}`);
            btn.disabled = false;
            btn.textContent = '📤 إرسال الملاحظة';
        }
    }

    // ======================= دوال إضافية =======================
    async function deleteAnswered() {
        if(!confirm('⚠️ حذف جميع الاستفسارات المجاب عليها؟')) return;
        try {
            const res = await fetch(`${BASE_URL}/delete_answered`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({admin_id: adminId}) });
            const data = await res.json();
            alert(`✅ تم حذف ${data.deleted || 0} استفسار`);
            loadQuestions();
        } catch(e){ alert(e.message); }
    }

    // ======================= تشغيل التطبيق =======================
    document.addEventListener('DOMContentLoaded', () => {
        if (!adminId) { document.body.innerHTML = '<div class="error" style="padding:40px;">❌ لم نتمكن من التعرف عليك. تأكد من فتح اللوحة من داخل تيليجرام.</div>'; return; }
        switchTab('ask');
        window.BOT_TOKEN = '';
    });
</script>
</body>
</html>
