'use strict';
(() => {
  // Cache frequently accessed DOM elements
  const chatMessagesEl = document.getElementById('chatMessages');
  const chatListEl = document.getElementById('chatList');
  const messageInputEl = document.getElementById('messageInput');
  const modelSelectEl = document.getElementById('model');
  const authContainerEl = document.getElementById('authContainer');
  const appContainerEl = document.getElementById('appContainer');
  const sidebarEl = document.getElementById('sidebar');
  const chatContainerEl = document.getElementById('chatContainer');
  const inputContainerEl = document.querySelector('#chatInputContainer');

  // Global state
  let token = '';
  let currentChatId = null;
  let lastUserMessage = '';
  let userPreferences = {};

  // Configure marked.js for code highlighting
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

  // ----------------------------
  // Helper Functions
  // ----------------------------
  const createMessageElement = (role) => {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${role}-message`);
    chatMessagesEl.appendChild(messageDiv);
    return messageDiv;
  };

  const clearMessages = () => {
    chatMessagesEl.innerHTML = '';
  };

  const updateURL = (chatId) => {
    const url = chatId ? `/${chatId}` : '/';
    window.history.pushState(chatId ? { chatId } : {}, '', url);
  };

  // ----------------------------
  // Browser Navigation
  // ----------------------------
  window.onpopstate = (event) => {
    if (event.state && event.state.chatId) {
      loadChat(event.state.chatId);
    } else {
      clearMessages();
      currentChatId = null;
    }
  };

  // ----------------------------
  // Initialization
  // ----------------------------
  const initChat = async () => {
    const pathParts = window.location.pathname.split('/');
    const chatId = pathParts[1] ? parseInt(pathParts[1], 10) : null;
    await loadUserPreferences();
    await updateChats();
    await updateModels();
    if (chatId) {
      await loadChat(chatId);
    }
    addFileUploadButton();
  };

  // ----------------------------
  // User Preferences
  // ----------------------------
  const loadUserPreferences = async () => {
    try {
      const response = await fetch('/preferences', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        userPreferences = await response.json();
        applyPreferences();
      }
    } catch (error) {
      console.error('Error loading preferences:', error);
    }
  };

  const applyPreferences = () => {
    document.body.className = userPreferences.theme || 'light';
    if (userPreferences.default_model && modelSelectEl) {
      modelSelectEl.value = userPreferences.default_model;
    }
  };

  // ----------------------------
  // Chat Management Functions
  // ----------------------------
  const createNewChat = async () => {
    const model = modelSelectEl.value;
    try {
      const response = await fetch('/chats', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: "",
          model: model,
          system_prompt: userPreferences.default_system_prompt
        })
      });
      if (response.ok) {
        const data = await response.json();
        currentChatId = data.chat_id;
        await updateChats();
        clearMessages();
        updateURL(currentChatId);
        return currentChatId;
      }
    } catch (error) {
      console.error('Error creating chat:', error);
    }
    return null;
  };

  async function loadChat(chatId) {
    try {
      const response = await fetch(`/chats/${chatId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        clearMessages();
        data.messages.forEach(msg => {
          const messageDiv = createMessageElement(msg.role);
          messageDiv.innerHTML = marked.parse(msg.content || '');
          messageDiv.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
          });
        });
        currentChatId = chatId;
        updateURL(chatId);
        highlightActiveChat(chatId);
      }
    } catch (error) {
      console.error('Error loading chat:', error);
    }
  }

  const highlightActiveChat = (chatId) => {
    document.querySelectorAll('.chat-item').forEach(item => item.classList.remove('active'));
    const activeChatEl = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
    if (activeChatEl) {
      activeChatEl.classList.add('active');
    }
  };

  const updateChats = async () => {
    try {
      const response = await fetch('/chats', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        chatListEl.innerHTML = data.chats
          .map(chat => {
            let displayTitle = chat.title
              .replace(/^Chat about /, '')
              .replace(/\.\.\.$/, '')
              .trim();
            const activeClass = chat.id === currentChatId ? 'active' : '';
            return `
              <div class="chat-item ${activeClass}" data-chat-id="${chat.id}">
                <span class="chat-title" title="${chat.title}">${displayTitle}</span>
                <button class="chat-menu-button" onclick="toggleChatMenu(event)">☰</button>
                <div class="chat-menu">
                  <button onclick="shareChat(${chat.id})">Share</button>
                  <button onclick="renameChat(${chat.id})">Rename</button>
                  <button onclick="deleteChat(${chat.id})">Delete</button>
                </div>
              </div>`;
          })
          .join('');
        document.querySelectorAll('.chat-item').forEach(item => {
          item.addEventListener('click', (e) => {
            if (
              e.target.classList.contains('chat-menu-button') ||
              (e.target.parentElement && e.target.parentElement.classList.contains('chat-menu'))
            ) {
              return;
            }
            const chatId = parseInt(item.getAttribute('data-chat-id'), 10);
            loadChat(chatId);
          });
        });
      }
    } catch (error) {
      console.error('Error updating chats:', error);
    }
  };

  // ----------------------------
  // File Handling
  // ----------------------------
  const addFileUploadButton = () => {
    if (!document.getElementById('fileButton')) {
      const fileButton = document.createElement('button');
      fileButton.id = 'fileButton';
      fileButton.textContent = 'Attach File';
      fileButton.addEventListener('click', () => {
        document.getElementById('fileInput').click();
      });
      inputContainerEl.appendChild(fileButton);
    }
    if (!document.getElementById('fileInput')) {
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.id = 'fileInput';
      fileInput.style.display = 'none';
      inputContainerEl.appendChild(fileInput);
      fileInput.addEventListener('change', handleFileUpload);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (!currentChatId) {
      await createNewChat();
    }
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await fetch(`/chat/${currentChatId}/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });
      if (response.ok) {
        const data = await response.json();
        messageInputEl.value += `\n[Attached file: ${data.filename}]`;
      }
    } catch (error) {
      console.error('Error uploading file:', error);
      alert('Failed to upload file');
    }
  };

  // ----------------------------
  // Message Handling
  // ----------------------------
  const style = document.createElement('style');
  style.textContent = `
    #chatMessages {
      scroll-behavior: smooth;
      padding-bottom: 20vh; /* Add padding at the bottom */
    }
  
    .message {
      opacity: 0;
      transform: translateY(20px);
      animation: fadeInUp 0.3s ease forwards;
    }
  
    @keyframes fadeInUp {
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  `;
  document.head.appendChild(style);
  
  const sendMessage = async () => {
    const message = messageInputEl.value.trim();
    const model = modelSelectEl.value;
    if (!message) return;
    lastUserMessage = message;

    if (!currentChatId) {
        const newChatId = await createNewChat();
        if (!newChatId) return;
    }

    const userMessageEl = createMessageElement('user');
    userMessageEl.innerHTML = marked.parse(message);
    messageInputEl.value = '';

    // Scroll to the bottom after user message
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

    const assistantMessageEl = createMessageElement('assistant');
    assistantMessageEl.textContent = "Assistant is typing...";

    // Store the initial scroll position
    const initialScrollTop = chatMessagesEl.scrollTop;
    const isAtBottom = chatMessagesEl.scrollHeight - chatMessagesEl.clientHeight <= chatMessagesEl.scrollTop + 50;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message,
                model,
                chat_id: currentChatId
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullMessage = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.response) {
                            fullMessage += data.response;
                            assistantMessageEl.innerHTML = marked.parse(fullMessage);
                            assistantMessageEl.querySelectorAll('pre code').forEach(block => {
                                hljs.highlightElement(block);
                            });
                            
                            // Only auto-scroll if user was already at bottom
                            if (isAtBottom) {
                                requestAnimationFrame(() => {
                                    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
                                });
                            }
                        }
                    } catch (e) {
                        console.error('JSON parse error:', e);
                    }
                }
            }
        }

    } catch (error) {
        console.error('Error in message streaming:', error);
        assistantMessageEl.textContent = 'Error: Failed to send message';
    }
};

  // ----------------------------
  // Chat Control Functions
  // ----------------------------
  window.newChat = async () => {
    await createNewChat();
    clearMessages();
  };

  window.exportChat = async () => {
    if (!currentChatId) {
      alert("No chat selected!");
      return;
    }
    try {
      const response = await fetch(`/chats/${currentChatId}/export`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat_${currentChatId}.txt`;
        document.body.appendChild(a);
        a.click();
        a.remove();
      } else {
        alert("Failed to export chat.");
      }
    } catch (error) {
      console.error('Error exporting chat:', error);
    }
  };

  // ----------------------------
  // Chat Menu Functions
  // ----------------------------
  window.toggleChatMenu = (event) => {
    event.stopPropagation();
    const button = event.currentTarget;
    const menu = button.nextElementSibling;
    
    document.querySelectorAll('.chat-menu').forEach(m => {
      if (m !== menu) m.style.display = 'none';
    });
    
    menu.style.display = menu.style.display === 'flex' ? 'none' : 'flex';
  };

  window.shareChat = (chatId) => {
    const chatUrl = window.location.origin + '/' + chatId;
    navigator.clipboard.writeText(chatUrl).then(() => {
      alert('Chat URL copied to clipboard!');
    });
  };

  window.renameChat = async (chatId) => {
    const newTitle = prompt("Enter new chat title:");
    if (!newTitle) return;
    try {
      const response = await fetch(`/chats/${chatId}/rename`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ title: newTitle })
      });
      if (response.ok) {
        alert('Chat renamed successfully');
        await updateChats();
      } else {
        alert('Failed to rename chat');
      }
    } catch (error) {
      console.error("Error renaming chat:", error);
    }
  };

  window.deleteChat = async (chatId) => {
    if (!confirm("Are you sure you want to delete this chat?")) return;
    try {
      const response = await fetch(`/chats/${chatId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        alert("Chat deleted successfully.");
        await updateChats();
        if (currentChatId === chatId) {
          clearMessages();
          currentChatId = null;
          updateURL(null);
        }
      } else {
        alert("Failed to delete chat.");
      }
    } catch (error) {
      console.error("Error deleting chat:", error);
    }
  };

  // ----------------------------
  // Authentication Functions
  // ----------------------------
  const login = async () => {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    try {
      const response = await fetch('/token', { method: 'POST', body: formData });
      if (response.ok) {
        const data = await response.json();
        token = data.access_token;
        localStorage.setItem('token', token);
        authContainerEl.style.display = 'none';
        appContainerEl.style.display = 'flex';
        sidebarEl.style.display = 'block';
        chatContainerEl.style.display = 'flex';
        await initChat();
      } else {
        alert('Login failed');
      }
    } catch (error) {
      console.error('Login error:', error);
      alert('Login failed');
    }
  };

  const logout = () => {
    token = '';
    localStorage.removeItem('token');
    authContainerEl.style.display = 'flex';
    appContainerEl.style.display = 'none';
    updateURL(null);
  };

  const showLogin = () => {
    authContainerEl.innerHTML = `
      <div class="auth-form">
        <h2>Login</h2>
        <div class="auth-input-group">
          <input type="text" id="username" placeholder="Username">
        </div>
        <div class="auth-input-group">
          <input type="password" id="password" placeholder="Password">
        </div>
        <div class="auth-input-group">
          <button id="loginButton">Login</button>
        </div>
        <div class="auth-input-group">
          <button id="goToRegister" class="secondary-button">Register</button>
        </div>
      </div>
    `;
    document.getElementById('loginButton').addEventListener('click', login);
    document.getElementById('goToRegister').addEventListener('click', showRegister);
  };

  const showRegister = () => {
    authContainerEl.innerHTML = `
      <div class="auth-form">
        <h2>Register</h2>
        <div class="auth-input-group">
          <input type="text" id="username" placeholder="Username">
        </div>
        <div class="auth-input-group">
          <input type="password" id="password" placeholder="Password">
        </div>
        <div class="auth-input-group">
          <button id="registerButton">Register</button>
        </div>
        <div class="auth-input-group">
          <button id="backToLogin" class="secondary-button">Back to Login</button>
        </div>
      </div>
    `;
    document.getElementById('registerButton').addEventListener('click', register);
    document.getElementById('backToLogin').addEventListener('click', showLogin);
  };

  const register = async () => {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    try {
      const response = await fetch('/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (response.ok) {
        alert('Registration successful! Please log in.');
        showLogin();
      } else {
        const errorData = await response.json();
        alert(`Registration failed: ${errorData.detail}`);
      }
    } catch (error) {
      console.error('Registration error:', error);
      alert('Registration failed');
    }
  };

  // ----------------------------
  // Models Management
  // ----------------------------
  const updateModels = async () => {
    try {
      const response = await fetch('/models', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        modelSelectEl.innerHTML = data.models
          .sort((a, b) => a.name.localeCompare(b.name))
          .map(model => `<option value="${model.name}">${model.name}</option>`)
          .join('');
      }
    } catch (error) {
      console.error('Error fetching models:', error);
    }
  };

  // ----------------------------
  // Check Authentication on Load
  // ----------------------------
  const checkAuthState = () => {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      token = storedToken;
      authContainerEl.style.display = 'none';
      appContainerEl.style.display = 'flex';
      sidebarEl.style.display = 'block';
      chatContainerEl.style.display = 'flex';
      initChat();
    } else {
      authContainerEl.style.display = 'flex';
      appContainerEl.style.display = 'none';
    }
  };

  // Hide open chat menus when clicking anywhere else
  document.addEventListener('click', () => {
    document.querySelectorAll('.chat-menu').forEach(menu => {
      menu.style.display = 'none';
    });
  });

  // Initialize event listeners
  document.addEventListener('DOMContentLoaded', () => {
    checkAuthState();
    messageInputEl.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  });

  // Export necessary functions to window object
  window.login = login;
  window.logout = logout;
  window.showRegister = showRegister;
  window.showLogin = showLogin;
  window.sendMessage = sendMessage;
})();