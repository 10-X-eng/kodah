'use strict';

(() => {
  /* ============================================================
   * DOM Elements Cache
   * ============================================================ */
  const Elements = {
    chatMessages: document.getElementById('chatMessages'),
    chatList: document.getElementById('chatList'),
    messageInput: document.getElementById('messageInput'),
    modelSelect: document.getElementById('model'),
    authContainer: document.getElementById('authContainer'),
    appContainer: document.getElementById('appContainer'),
    sidebar: document.getElementById('sidebar'),
    chatContainer: document.getElementById('chatContainer'),
    inputContainer: document.querySelector('#chatInputContainer')
  };

  /* ============================================================
   * Application State
   * ============================================================ */
  const State = {
    token: '',
    currentChatId: null,
    lastUserMessage: '',
    userPreferences: {},
    availableModels: new Map(),
    eventListenersSetup: false
  };

  /* ============================================================
   * API Service
   * ============================================================ */
  const API = {
    async request(endpoint, options = {}) {
      const defaultHeaders = {
        'Authorization': `Bearer ${State.token}`,
        'Content-Type': 'application/json'
      };

      const config = {
        headers: { ...defaultHeaders, ...options.headers },
        ...options
      };

      try {
        const response = await fetch(`/api${endpoint}`, config);
        if (response.status === 401) {
          logout();
          throw new Error('Unauthorized');
        }
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response;
      } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
      }
    },

    async login(username, password) {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      return await this.request('/auth/token', {
        method: 'POST',
        headers: {},
        body: formData
      });
    },

    async register(username, password) {
      return await this.request('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, password })
      });
    },

    async createChat(title, model, systemPrompt) {
      return await this.request('/chat/create', {
        method: 'POST',
        body: JSON.stringify({ title, model, system_prompt: systemPrompt })
      });
    },

    async getChats() {
      return await this.request('/chat/list');
    },

    async getChatMessages(chatId) {
      return await this.request(`/chat/${chatId}/messages`);
    },

    async sendMessage(message, model, chatId) {
      return await this.request('/chat/message', {
        method: 'POST',
        body: JSON.stringify({ message, model, chat_id: chatId })
      });
    },

    async deleteChat(chatId) {
      return await this.request(`/chat/${chatId}`, { method: 'DELETE' });
    },

    async regenerateMessage(chatId, messageIndex) {
      return await this.request('/chat/regenerate', {
        method: 'POST',
        body: JSON.stringify({ chat_id: chatId, message_index: messageIndex })
      });
    },

    async uploadFile(chatId, file) {
      const formData = new FormData();
      formData.append('file', file);
      return await this.request(`/files/${chatId}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${State.token}` },
        body: formData
      });
    },

    async exportChat(chatId) {
      return await this.request(`/files/export/${chatId}`);
    },

    async getUserPreferences() {
      return await this.request('/preferences');
    },

    async setUserPreferences(preferences) {
      return await this.request('/preferences', {
        method: 'POST',
        body: JSON.stringify(preferences)
      });
    },

    async getModels() {
      return await this.request('/models');
    }
  };

  /* ============================================================
   * UI Utilities
   * ============================================================ */
  const UI = {
    createMessageElement(role) {
      const messageDiv = document.createElement('div');
      messageDiv.classList.add('message', `${role}-message`);
      Elements.chatMessages.appendChild(messageDiv);
      return messageDiv;
    },

    clearMessages() {
      Elements.chatMessages.innerHTML = '';
    },

    updateURL(chatId) {
      const url = chatId ? `/${chatId}` : '/';
      window.history.pushState(chatId ? { chatId } : {}, '', url);
    },

    highlightActiveChat(chatId) {
      document.querySelectorAll('.chat-item').forEach(item =>
        item.classList.remove('active')
      );
      const activeChatEl = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
      if (activeChatEl) {
        activeChatEl.classList.add('active');
      }
    },

    showAuthForm(isLogin = true) {
      const formHTML = `
        <div class="auth-form">
          <h2>${isLogin ? 'Kodah Login' : 'Kodah Register'}</h2>
          <div class="auth-input-group">
            <input type="text" id="username" placeholder="Username">
          </div>
          <div class="auth-input-group">
            <input type="password" id="password" placeholder="Password">
          </div>
          <div class="auth-input-group">
            <button id="${isLogin ? 'loginButton' : 'registerButton'}">
              ${isLogin ? 'Login' : 'Register'}
            </button>
          </div>
          <div class="auth-input-group">
            <button id="${isLogin ? 'goToRegister' : 'backToLogin'}" class="secondary-button">
              ${isLogin ? 'Register' : 'Back to Login'}
            </button>
          </div>
        </div>
      `;
      Elements.authContainer.innerHTML = formHTML;
      this.setupAuthEventListeners(isLogin);
    },

    setupAuthEventListeners(isLogin) {
      if (isLogin) {
        document.getElementById('loginButton').addEventListener('click', handleLogin);
        document.getElementById('goToRegister').addEventListener('click', () => UI.showAuthForm(false));
      } else {
        document.getElementById('registerButton').addEventListener('click', handleRegister);
        document.getElementById('backToLogin').addEventListener('click', () => UI.showAuthForm(true));
      }
    },

    updateChatList(chats) {
      Elements.chatList.innerHTML = chats
        .map(chat => {
          const displayTitle = chat.title.replace(/^Chat about /, '').replace(/\.\.\.$/, '').trim();
          const activeClass = chat.id === State.currentChatId ? 'active' : '';
          return `
            <div class="chat-item ${activeClass}" data-chat-id="${chat.id}">
              <span class="chat-title" title="${chat.title}">${displayTitle}</span>
              <button class="chat-menu-button" onclick="window.app.toggleChatMenu(event)">☰</button>
              <div class="chat-menu">
                <button onclick="window.app.renameChat(${chat.id})">Rename</button>
                <button onclick="window.app.deleteChat(${chat.id})">Delete</button>
              </div>
            </div>`;
        })
        .join('');
      
      document.querySelectorAll('.chat-item').forEach(item => {
        item.addEventListener('click', (e) => {
          if (e.target.closest('.chat-menu') || e.target.classList.contains('chat-menu-button')) return;
          const chatId = parseInt(item.getAttribute('data-chat-id'), 10);
          handleChatSelection(chatId);
        });
      });
    }
  };

  /* ============================================================
   * Event Handlers
   * ============================================================ */
  async function handleLogin() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    if (!username || !password) {
      alert('Please enter both username and password');
      return;
    }
    try {
      const response = await API.login(username, password);
      if (!response.ok) throw new Error('Invalid credentials');
      const data = await response.json();
      State.token = data.access_token;
      localStorage.setItem('token', State.token);
      Elements.authContainer.style.display = 'none';
      Elements.appContainer.style.display = 'flex';
      Elements.sidebar.style.display = 'block';
      Elements.chatContainer.style.display = 'flex';
      await initializeApp();
    } catch (error) {
      alert('Login failed: ' + (error.message || 'Invalid username or password'));
    }
  }

  async function handleRegister() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    try {
      await API.register(username, password);
      alert('Registration successful! Please log in.');
      UI.showAuthForm(true);
    } catch (error) {
      alert('Registration failed');
    }
  }

  async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!State.currentChatId) await createNewChat();
    try {
      const response = await API.uploadFile(State.currentChatId, file);
      const data = await response.json();
      Elements.messageInput.value += `\n[Attached file: ${data.filename}]`;
    } catch (error) {
      alert('Failed to upload file');
    }
  }

  async function handleChatSelection(chatId) {
    try {
      const response = await API.getChatMessages(chatId);
      const data = await response.json();
      UI.clearMessages();
      data.messages.forEach((msg) => {
        const messageDiv = UI.createMessageElement(msg.role);
        messageDiv.innerHTML = marked.parse(msg.content || "");
        messageDiv.querySelectorAll("pre code").forEach((block) =>
          hljs.highlightElement(block)
        );
      });
      addCopyButtons();
      State.currentChatId = chatId;
      UI.updateURL(chatId);
      UI.highlightActiveChat(chatId);
      setTimeout(() => {
        Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
      }, 100);
    } catch (error) {
      console.error("Error loading chat:", error);
    }
  }

  async function sendMessage() {
    const message = Elements.messageInput.value.trim();
    if (!message) return;
    
    State.lastUserMessage = message;
  
    // Create user message bubble
    const userMessageEl = UI.createMessageElement("user");
    userMessageEl.innerHTML = marked.parse(message);
    Elements.messageInput.value = "";
    Elements.messageInput.style.height = "2.5rem";
    
    if (!State.currentChatId) {
      const newChatId = await createNewChat();
      if (!newChatId) return;
    }
  
    // Create assistant message container
    const assistantMessageEl = document.createElement('div');
    assistantMessageEl.classList.add('message', 'assistant-message');
    
    // Create containers for chain-of-thought and final answer
    const chainContainer = document.createElement('div');
    chainContainer.classList.add('chain-of-thought-container');
    
    const finalContainer = document.createElement('div');
    finalContainer.classList.add('final-answer-container');
    finalContainer.style.display = 'none';
    
    // Add typing indicator
    const indicatorSpan = document.createElement('span');
    indicatorSpan.classList.add('assistant-indicator');
    indicatorSpan.style.marginLeft = "8px";
    
    assistantMessageEl.appendChild(chainContainer);
    assistantMessageEl.appendChild(finalContainer);
    assistantMessageEl.appendChild(indicatorSpan);
    
    // Initialize typing indicator animation
    let dotCount = 0;
    const loadingInterval = setInterval(() => {
      dotCount = (dotCount + 1) % 4;
      indicatorSpan.textContent = "Assistant is typing" + ".".repeat(dotCount);
    }, 500);
    Elements.chatMessages.appendChild(assistantMessageEl);
  
    // Track the current chain of thought
    let currentChain = '';
    let finalAnswer = '';
    let criticResponses = [];
    let responderResponses = [];
  
    try {
      const response = await API.sendMessage(
        message,
        Elements.modelSelect.value,
        State.currentChatId
      );
  
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
  
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
  
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
  
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'chain') {
                // Clear previous chain content
                chainContainer.innerHTML = '';
                
                // Store the responses based on role
                if (data.content.includes('Critic:')) {
                  criticResponses.push(data.content);
                } else if (data.content.includes('Responder:')) {
                  responderResponses.push(data.content);
                }
                
                // Display current chain
                const chainContent = document.createElement('div');
                chainContent.innerHTML = marked.parse(data.content);
                chainContainer.appendChild(chainContent);
                
                // Highlight the role
                const roleSpan = document.createElement('span');
                roleSpan.classList.add('reasoning-role');
                roleSpan.textContent = data.content.includes('Critic:') ? 'Critic' : 'Responder';
                chainContainer.insertBefore(roleSpan, chainContent);
                
              } else if (data.type === 'final') {
                // Hide chain container and show final answer
                chainContainer.style.display = 'none';
                finalContainer.style.display = 'block';
                
                finalAnswer = data.content;
                finalContainer.innerHTML = marked.parse(finalAnswer);
                
                // Add a collapsible section for the reasoning chain
                const reasoningToggle = document.createElement('button');
                reasoningToggle.classList.add('reasoning-toggle');
                reasoningToggle.textContent = 'Show reasoning';
                
                reasoningToggle.addEventListener('click', () => {
                  const isExpanded = reasoningToggle.classList.contains('expanded');
                  if (isExpanded) {
                    chainContainer.style.display = 'none';
                    reasoningToggle.textContent = 'Show reasoning';
                  } else {
                    chainContainer.style.display = 'block';
                    reasoningToggle.textContent = 'Hide reasoning';
                  }
                  reasoningToggle.classList.toggle('expanded');
                });
                
                assistantMessageEl.insertBefore(reasoningToggle, finalContainer);
              }
            } catch (e) {
              console.error('Error parsing chunk:', e);
            }
          }
        }
        
        // Scroll to bottom after each update
        Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
      }
    } catch (error) {
      console.error('Error in message handling:', error);
      chainContainer.innerHTML = 'Error: Failed to send message';
    } finally {
      // Clean up the typing indicator
      clearInterval(loadingInterval);
      indicatorSpan.remove();
    }
  }
  
  async function initializeApp() {
    const pathParts = window.location.pathname.split('/');
    const chatId = pathParts[1] ? parseInt(pathParts[1], 10) : null;
    await Promise.all([
      loadUserPreferences(),
      updateChats(),
      updateModels()
    ]);
    if (chatId) {
      await handleChatSelection(chatId);
    }
  }

  async function loadUserPreferences() {
    try {
      const response = await API.getUserPreferences();
      State.userPreferences = await response.json();
      applyPreferences();
    } catch (error) {
      console.error('Error loading preferences:', error);
    }
  }

  function applyPreferences() {
    document.body.className = State.userPreferences.theme || 'light';
    if (State.userPreferences.default_model && Elements.modelSelect) {
      Elements.modelSelect.value = State.userPreferences.default_model;
    }
    console.log("Use reasoning:", State.userPreferences.use_reasoning);
  }

  async function updateChats() {
    try {
      const response = await API.getChats();
      const data = await response.json();
      UI.updateChatList(data.chats);
    } catch (error) {
      console.error('Error updating chats:', error);
    }
  }

  async function updateModels() {
    try {
      const response = await API.getModels();
      const data = await response.json();
      if (data.models && data.models.length > 0) {
        Elements.modelSelect.innerHTML = data.models
          .sort((a, b) => a.name.localeCompare(b.name))
          .map(model => `<option value="${model.name}">${model.name}</option>`)
          .join('');
        console.log('Models loaded successfully:', data.models.length, 'models available');
      } else {
        Elements.modelSelect.innerHTML = '<option value="">No models available...</option>';
        setTimeout(updateModels, 5000);
      }
    } catch (error) {
      console.error('Error fetching models:', error);
      Elements.modelSelect.innerHTML = '<option value="">Error loading models...</option>';
      setTimeout(updateModels, 5000);
    }
  }

  async function refreshChatTitle(chatId) {
    try {
      const response = await API.request(`/chat/${chatId}/details`);
      if (response.ok) {
        const details = await response.json();
        if (details.title && details.title !== 'New Chat...') {
          const chatTitleElem = document.querySelector(`.chat-item[data-chat-id="${chatId}"] .chat-title`);
          if (chatTitleElem) {
            chatTitleElem.textContent = details.title;
            chatTitleElem.setAttribute('title', details.title);
          }
        }
      }
    } catch (error) {
      console.error('Error refreshing chat title:', error);
    }
  }

  async function createNewChat() {
    const model = Elements.modelSelect.value;
    try {
      const response = await API.createChat('', model, State.userPreferences.default_system_prompt);
      const data = await response.json();
      State.currentChatId = data.chat_id;
      await updateChats();
      UI.clearMessages();
      UI.updateURL(State.currentChatId);
      return State.currentChatId;
    } catch (error) {
      console.error('Error creating chat:', error);
      return null;
    }
  }

  async function exportChat() {
    if (!State.currentChatId) {
      showAlert('No chat selected!', { autoDismiss: true, duration: 500 });
      return;
    }
    try {
      const response = await API.exportChat(State.currentChatId);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chat_${State.currentChatId}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      showAlert('Failed to export chat.', { autoDismiss: false });
    }
  }

  function toggleChatMenu(event) {
    event.stopPropagation();
    const button = event.currentTarget;
    const menu = button.nextElementSibling;
    document.querySelectorAll('.chat-menu').forEach(m => {
      if (m !== menu) m.classList.remove('show');
    });
    menu.classList.toggle('show');
  }

  function shareChat(chatId) {
    const chatUrl = window.location.origin + '/' + chatId;
    navigator.clipboard.writeText(chatUrl)
      .then(() => alert('Chat URL copied to clipboard!'))
      .catch(() => alert('Failed to copy URL to clipboard'));
  }

  async function renameChat(chatId) {
    const newTitle = prompt('Enter new chat title:');
    if (!newTitle) return;
    try {
      const response = await API.request(`/chat/${chatId}/rename`, {
        method: 'PUT',
        body: JSON.stringify({ title: newTitle })
      });
      if (response.ok) {
        await updateChats();
      } else {
        alert('Failed to rename chat');
      }
    } catch (error) {
      console.error('Error renaming chat:', error);
      alert('Failed to rename chat');
    }
  }

  async function deleteChat(chatId) {
    if (!(await showConfirm('Are you sure you want to delete this chat?'))) return;
    try {
      await API.deleteChat(chatId);
      showAlert('Chat deleted successfully.', { autoDismiss: true, duration: 1000 });
      await updateChats();
      if (State.currentChatId === chatId) {
        UI.clearMessages();
        State.currentChatId = null;
        UI.updateURL(null);
      }
    } catch (error) {
      console.error('Error deleting chat:', error);
      showAlert('Error: Unable to delete chat. Please try again.', { autoDismiss: false });
    }
  }

  function logout() {
    State.token = '';
    localStorage.removeItem('token');
    Elements.authContainer.style.display = 'flex';
    Elements.appContainer.style.display = 'none';
    UI.updateURL(null);
  }

  function checkAuthState() {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      State.token = storedToken;
      Elements.authContainer.style.display = 'none';
      Elements.appContainer.style.display = 'flex';
      Elements.sidebar.style.display = 'block';
      Elements.chatContainer.style.display = 'flex';
      initializeApp();
    } else {
      Elements.authContainer.style.display = 'flex';
      Elements.appContainer.style.display = 'none';
      UI.showAuthForm(true);
    }
  }

  marked.setOptions({
    highlight: (code, language) => {
      if (language && hljs.getLanguage(language)) {
        try {
          return hljs.highlight(code, { language }).value;
        } catch (err) {
          console.error('Highlight error:', err);
        }
      }
      return code;
    }
  });

  function addCopyButtons() {
    document.querySelectorAll("pre").forEach(pre => {
      if (pre.querySelector(".copy-btn")) return;
      const button = document.createElement("button");
      button.className = "copy-btn";
      button.innerHTML = '<i class="fa-regular fa-copy"></i>';
      button.addEventListener("click", () => {
        const codeEl = pre.querySelector("code");
        if (!codeEl) return;
        const codeText = codeEl.innerText;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(codeText)
            .then(() => {
              button.innerHTML = '<i class="fa-regular fa-circle-check"></i>';
              setTimeout(() => { button.innerHTML = '<i class="fa-regular fa-copy"></i>'; }, 2000);
            })
            .catch(err => {
              console.error("Clipboard API error, using fallback:", err);
              copyTextFallback(codeText);
              button.innerHTML = '<i class="fa-regular fa-circle-check"></i>';
              setTimeout(() => { button.innerHTML = '<i class="fa-regular fa-copy"></i>'; }, 2000);
            });
        } else {
          copyTextFallback(codeText);
          button.innerHTML = '<i class="fa-regular fa-circle-check"></i>';
          setTimeout(() => { button.innerHTML = '<i class="fa-regular fa-copy"></i>'; }, 2000);
        }
      });
      pre.style.position = "relative";
      pre.appendChild(button);
    });
  }
  
  function copyTextFallback(text) {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.top = "0";
    textArea.style.left = "0";
    textArea.style.position = "fixed";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      const successful = document.execCommand('copy');
      if (!successful) console.error("Fallback: Copy unsuccessful");
    } catch (err) {
      console.error("Fallback: Unable to copy", err);
    }
    document.body.removeChild(textArea);
  }
  
  const style = document.createElement('style');
  style.textContent = `
    #chatMessages { scroll-behavior: smooth; padding-bottom: 20vh; }
    .message { opacity: 0; transform: translateY(20px); animation: fadeInUp 0.3s ease forwards; }
    @keyframes fadeInUp { to { opacity: 1; transform: translateY(0); } }
    .chain-of-thought { color: #555; font-style: italic; }
    .final-answer { color: #000; }
    .error { color: red; }
  `;
  document.head.appendChild(style);

  window.onpopstate = (event) => {
    if (event.state && event.state.chatId) {
      handleChatSelection(event.state.chatId);
    } else {
      UI.clearMessages();
      State.currentChatId = null;
    }
  };

  // Preferences Modal functions
  function showPreferencesModal() {
    // Prevent duplicate modal insertion
    if (document.getElementById('preferencesModalOverlay')) return;
    
    const modalHTML = `
      <div class="modal-overlay" id="preferencesModalOverlay">
        <div class="modal">
          <h3>User Preferences</h3>
          <label>
            Default Model:
            <input type="text" id="prefDefaultModel" value="${State.userPreferences.default_model || ''}">
          </label>
          <label>
            Theme:
            <select id="prefTheme">
              <option value="light" ${State.userPreferences.theme === 'light' ? 'selected' : ''}>Light</option>
              <option value="dark" ${State.userPreferences.theme === 'dark' ? 'selected' : ''}>Dark</option>
            </select>
          </label>
          <label>
            Default System Prompt:
            <textarea id="prefSystemPrompt">${State.userPreferences.default_system_prompt || ''}</textarea>
          </label>
          <label>
            <input type="checkbox" id="prefUseReasoning" ${State.userPreferences.use_reasoning ? 'checked' : ''}>
            Enable Reasoning
          </label>
          <button id="savePreferencesButton">Save Preferences</button>
          <button id="cancelPreferencesButton">Cancel</button>
        </div>
      </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    // Immediately add the "show" class to make it visible.
    document.getElementById('preferencesModalOverlay').classList.add('show');
    
    document.getElementById('savePreferencesButton').addEventListener('click', async () => {
      const newPrefs = {
        default_model: document.getElementById('prefDefaultModel').value,
        theme: document.getElementById('prefTheme').value,
        default_system_prompt: document.getElementById('prefSystemPrompt').value,
        use_reasoning: document.getElementById('prefUseReasoning').checked
      };
      try {
        await API.setUserPreferences(newPrefs);
        State.userPreferences = { ...State.userPreferences, ...newPrefs };
        applyPreferences();
        closePreferencesModal();
      } catch (e) {
        alert('Failed to save preferences');
      }
    });
    
    document.getElementById('cancelPreferencesButton').addEventListener('click', closePreferencesModal);
  }
  
  
  function closePreferencesModal() {
    const overlay = document.getElementById('preferencesModalOverlay');
    if (overlay) overlay.remove();
  }
  
  // Attach gear icon event listener
  document.getElementById('preferencesButton').addEventListener('click', showPreferencesModal);

  document.addEventListener('click', (event) => {
    if (!event.target.closest('.chat-menu') && !event.target.closest('.chat-menu-button')) {
      document.querySelectorAll('.chat-menu').forEach(menu => menu.classList.remove('show'));
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    const messageInput = document.getElementById("messageInput");
    messageInput.addEventListener("input", function () {
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 160) + "px";
    });
    messageInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    });
  });
  
  document.addEventListener('DOMContentLoaded', checkAuthState);

  window.app = {
    newChat: createNewChat,
    exportChat,
    shareChat,
    renameChat,
    deleteChat,
    toggleChatMenu,
    sendMessage,
    logout,
    login: handleLogin,
    showRegister: () => UI.showAuthForm(false),
    showLogin: () => UI.showAuthForm(true)
  };
})();
