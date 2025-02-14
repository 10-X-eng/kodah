# Kodah - Advanced Web UI for Ollama

Kodah is a sophisticated web interface for Ollama that provides an enhanced chat experience with advanced features like conversation management, authentication, and contextual reasoning. It's built with FastAPI and modern web technologies to provide a responsive and user-friendly interface for interacting with Ollama models.



## Features

These features are still very much a work in progress. None of them are 100% complete, as a matter of fact most of them are less than 25% 

- 🔒 **Secure Authentication**: User registration and login system with token-based authentication
- 💬 **Chat Management**: Create, rename, and organize multiple chat conversations
- 🤖 **Model Selection**: Dynamically loads and allows selection of available Ollama models
- 🧠 **Advanced Reasoning**: Optional chain-of-thought reasoning system for more detailed responses
- 🌙 **Theme Support**: Light and dark theme options for comfortable viewing
- 📝 **Context Management**: Intelligent context handling with automatic summarization
- 📤 **File Handling**: Upload and manage files within conversations
- 📋 **Copy & Export**: Easy code copying and chat export functionality
- ⚡ **Streaming Responses**: Real-time streaming of model responses
- 🎯 **User Preferences**: Customizable settings for model, theme, and system prompts

## Installation

### Prerequisites

- Python 3.8 or higher
- Ollama installed and running
- SQLite (included in Python)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/10-X-eng/kodah.git
cd kodah
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install fastapi uvicorn httpx sqlite3 hnswlib sentence-transformers
```

4. Set up the configuration:
Create a `.env` file in the root directory with the following settings:
```env
OLLAMA_API_URL=http://localhost:11434
DATABASE_PATH=./database.sqlite
UPLOAD_DIR=./uploads
SECRET_KEY=your-secret-key
```

5. Create the uploads directory:
```bash
mkdir uploads
```

### Running the Application

1. Start the server:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

2. Access the web interface at `http://localhost:8000`

## Usage

### First Time Setup

1. Register a new account using the registration form
2. Log in with your credentials
3. The interface will automatically detect available Ollama models

### Basic Features

- **Create a New Chat**: Click the "New Chat" button in the sidebar
- **Send Messages**: Type in the input box and press Enter (Shift+Enter for new line)
- **Switch Models**: Select different models from the dropdown menu
- **Upload Files**: Click the upload button to attach files to your messages
- **Export Chats**: Use the export option in the chat menu to save conversations

### Advanced Features

#### User Preferences
Access the preferences menu to customize:
- Default model selection
- Interface theme (light/dark)
- System prompts
- Reasoning mode (enable/disable chain-of-thought)

#### Chat Management
- Rename chats for better organization
- Delete unwanted conversations
- Share chat links with other users

#### Reasoning Mode
When enabled, the assistant will:
1. Generate an initial response
2. Analyze it with a critic
3. Respond to criticism
4. Provide a final, refined answer

## Configuration

The application can be configured through environment variables or a `.env` file:

- `OLLAMA_API_URL`: URL of your Ollama instance
- `DATABASE_PATH`: Path to SQLite database file
- `UPLOAD_DIR`: Directory for uploaded files
- `SECRET_KEY`: Secret key for JWT token generation
- `MAX_CONTEXT_LENGTH`: Maximum context length for conversations

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Powered by [Ollama](https://ollama.ai/)
- Uses [sentence-transformers](https://www.sbert.net/) for context management