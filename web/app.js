const SERVER_URL = 'http://localhost:7900';

// DOM Elements
const platformFilter = document.getElementById('platform-filter');
const searchInput = document.getElementById('search-input');
const conversationsList = document.getElementById('conversations-list');
const conversationDetail = document.getElementById('conversation-detail');
const messagesContainer = document.getElementById('messages');
const backBtn = document.getElementById('back-btn');

let currentConversations = [];

// Initialize
async function init() {
  await loadConversations();

  // Event listeners
  platformFilter.addEventListener('change', filterConversations);
  searchInput.addEventListener('input', filterConversations);
  backBtn.addEventListener('click', showConversationsList);
}

// Load conversations from server
async function loadConversations() {
  try {
    const response = await fetch(`${SERVER_URL}/api/conversations`);
    currentConversations = await response.json();
    renderConversations(currentConversations);
  } catch (error) {
    console.error('Failed to load conversations:', error);
    conversationsList.innerHTML = '<p>Error: Cannot connect to server. Make sure the server is running.</p>';
  }
}

// Render conversations list
function renderConversations(conversations) {
  if (conversations.length === 0) {
    conversationsList.innerHTML = '<p>No conversations found.</p>';
    return;
  }

  conversationsList.innerHTML = conversations.map(conv => `
    <div class="conversation-item" data-platform="${conv.platform}" data-session-id="${conv.session_id}">
      <h3>${escapeHtml(conv.title || 'Untitled')}</h3>
      <div class="meta">
        <span>${conv.platform}</span> |
        <span>${conv.message_count} messages</span> |
        <span>${new Date(conv.updated_at).toLocaleDateString()}</span>
      </div>
    </div>
  `).join('');

  // Add click handlers
  document.querySelectorAll('.conversation-item').forEach(item => {
    item.addEventListener('click', () => {
      const platform = item.dataset.platform;
      const sessionId = item.dataset.sessionId;
      showConversation(platform, sessionId);
    });
  });
}

// Filter conversations
function filterConversations() {
  const platform = platformFilter.value;
  const query = searchInput.value.toLowerCase();

  let filtered = currentConversations;

  if (platform) {
    filtered = filtered.filter(c => c.platform === platform);
  }

  if (query) {
    filtered = filtered.filter(c =>
      c.title.toLowerCase().includes(query) ||
      c.session_id.toLowerCase().includes(query)
    );
  }

  renderConversations(filtered);
}

// Show conversation detail
async function showConversation(platform, sessionId) {
  try {
    const response = await fetch(`${SERVER_URL}/api/conversations/${platform}/${sessionId}`);
    const data = await response.json();

    const { metadata, messages } = data;

    document.querySelector('.conversations').style.display = 'none';
    conversationDetail.style.display = 'block';

    conversationDetail.querySelector('h2')?.remove();
    const h2 = document.createElement('h2');
    h2.textContent = metadata.title || 'Untitled';
    conversationDetail.insertBefore(h2, backBtn);

    messagesContainer.innerHTML = messages.map(msg => `
      <div class="message ${msg.role}">
        <div class="role">${msg.role}</div>
        <div class="content">${escapeHtml(msg.content)}</div>
      </div>
    `).join('');

    window.scrollTo(0, 0);
  } catch (error) {
    console.error('Failed to load conversation:', error);
  }
}

// Show conversations list
function showConversationsList() {
  conversationDetail.style.display = 'none';
  document.querySelector('.conversations').style.display = 'block';
}

// Escape HTML
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Start
init();
