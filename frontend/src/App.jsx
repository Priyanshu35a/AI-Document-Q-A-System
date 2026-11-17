import React, { useState, useEffect, useRef } from 'react';
import {
  BookOpen,
  UploadCloud,
  Send,
  Trash2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Layers,
  Database,
  RefreshCw,
  CheckCircle2,
  FileCheck,
  Table,
  Download,
  Search,
  User as UserIcon,
  LogOut,
  Lock,
  Mail,
  FileText,
  Copy,
  ExternalLink,
  X,
  Settings,
  Server,
  Wifi,
  WifiOff,
  Check
} from 'lucide-react';

export default function App() {
  // Authentication State
  const [token, setToken] = useState(() => localStorage.getItem('rag_token') || '');
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('rag_user') || 'null');
    } catch {
      return null;
    }
  });

  // Backend API URL Configuration
  const [backendUrl, setBackendUrl] = useState(() => {
    return (
      localStorage.getItem('rag_backend_url') ||
      import.meta.env.VITE_BACKEND_URL ||
      import.meta.env.VITE_API_URL ||
      ''
    );
  });
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [tempBackendUrl, setTempBackendUrl] = useState(backendUrl);
  const [serverSaveSuccess, setServerSaveSuccess] = useState(false);

  const saveBackendUrl = (newUrl) => {
    const trimmed = (newUrl || '').trim().replace(/\/$/, '');
    setBackendUrl(trimmed);
    if (trimmed) {
      localStorage.setItem('rag_backend_url', trimmed);
    } else {
      localStorage.removeItem('rag_backend_url');
    }
    setServerSaveSuccess(true);
    setTimeout(() => setServerSaveSuccess(false), 2000);
    fetchHealth(trimmed);
  };

  const apiUrl = (path, overrideBase = null) => {
    const base = (overrideBase !== null ? overrideBase : backendUrl).replace(/\/$/, '');
    if (!base) return path;
    return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  };

  // Safe JSON extraction helper
  const safeJson = async (res) => {
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) return null;
    try {
      return await res.json();
    } catch {
      return null;
    }
  };

  // Auth Modal State
  const [authMode, setAuthMode] = useState('login'); // 'login' or 'signup'
  const [authUsername, setAuthUsername] = useState('');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  // App Navigation & Views
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' or 'sheet'
  const [sheetSubTab, setSheetSubTab] = useState('documents'); // 'documents' or 'chunks'

  // Chat & Document State
  const [health, setHealth] = useState(null);
  const isBackendOnline = Boolean(
    health && (health.status === 'online' || health.status === 'healthy')
  );
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState('all');
  const [messages, setMessages] = useState([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [expandedCitations, setExpandedCitations] = useState({});
  const [dragActive, setDragActive] = useState(false);

  // Sheet Data State
  const [sheetSummary, setSheetSummary] = useState(null);
  const [sheetDocs, setSheetDocs] = useState([]);
  const [sheetChunks, setSheetChunks] = useState([]);
  const [sheetSearch, setSheetSearch] = useState('');
  const [sheetLoading, setSheetLoading] = useState(false);
  const [inspectedCell, setInspectedCell] = useState(null);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // Authenticated fetch wrapper
  const authFetch = (path, options = {}) => {
    const url = path.startsWith('http') ? path : apiUrl(path);
    const headers = {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    return fetch(url, { ...options, headers });
  };

  // Check health on mount and backendUrl changes
  useEffect(() => {
    fetchHealth();
  }, [backendUrl]);

  // Initial Load when token is present
  useEffect(() => {
    if (token) {
      fetchHealth();
      fetchDocuments();
      fetchChatHistory();
      fetchSheetData();
    }
  }, [token, backendUrl]);

  // Auto-scroll chat
  useEffect(() => {
    if (activeTab === 'chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isGenerating, activeTab]);

  // Auth Actions
  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthError('');
    setAuthLoading(true);

    try {
      let endpoint = authMode === 'signup' ? '/api/auth/signup' : '/api/auth/login';
      let payload =
        authMode === 'signup'
          ? { username: authUsername.trim(), email: authEmail.trim(), password: authPassword }
          : { identifier: authEmail.trim(), password: authPassword };

      const res = await fetch(apiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const contentType = res.headers.get('content-type') || '';
      let data;
      if (contentType.includes('application/json')) {
        data = await res.json();
      } else {
        throw new Error(
          `Unable to reach backend API (status ${res.status}). If deployed on Netlify, configure your backend server URL in the "Server Settings" below.`
        );
      }

      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed');
      }

      // Save token and user
      localStorage.setItem('rag_token', data.token);
      localStorage.setItem('rag_user', JSON.stringify(data.user));
      setToken(data.token);
      setUser(data.user);
      setAuthPassword('');
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await authFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      console.error(e);
    }
    localStorage.removeItem('rag_token');
    localStorage.removeItem('rag_user');
    setToken('');
    setUser(null);
    setDocuments([]);
    setMessages([]);
    setSheetDocs([]);
    setSheetChunks([]);
  };

  const fetchHealth = async (customBase = null) => {
    try {
      const res = await fetch(apiUrl('/api/health', customBase));
      const data = await safeJson(res);
      if (res.ok && data) {
        setHealth(data);
      } else {
        setHealth({ status: 'unreachable' });
      }
    } catch (err) {
      setHealth({ status: 'unreachable' });
    }
  };

  const fetchDocuments = async () => {
    try {
      const res = await authFetch('/api/documents');
      if (res.status === 401) {
        handleLogout();
        return;
      }
      if (res.ok) {
        const data = await safeJson(res);
        if (data) setDocuments(data);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    }
  };

  const fetchChatHistory = async () => {
    try {
      const res = await authFetch('/api/chat/history');
      if (res.ok) {
        const data = await safeJson(res);
        if (data) setMessages(data);
      }
    } catch (err) {
      console.error('Failed to fetch chat history:', err);
    }
  };

  const fetchSheetData = async () => {
    setSheetLoading(true);
    try {
      const [sumRes, docsRes, chunksRes] = await Promise.all([
        authFetch('/api/sheets/summary'),
        authFetch('/api/sheets/documents'),
        authFetch(`/api/sheets/chunks?search=${encodeURIComponent(sheetSearch)}`)
      ]);

      if (sumRes.ok) {
        const data = await safeJson(sumRes);
        if (data) setSheetSummary(data);
      }
      if (docsRes.ok) {
        const data = await safeJson(docsRes);
        if (data) setSheetDocs(data);
      }
      if (chunksRes.ok) {
        const cData = await safeJson(chunksRes);
        if (cData) setSheetChunks(cData.rows || []);
      }
    } catch (err) {
      console.error('Error fetching sheet data:', err);
    } finally {
      setSheetLoading(false);
    }
  };

  // Upload handler
  const handleFileUpload = async (file) => {
    if (!file) return;
    const allowed = ['.pdf', '.png', '.jpg', '.jpeg', '.webp'];
    const fileName = file.name.toLowerCase();
    const isSupported = allowed.some((ext) => fileName.endsWith(ext));
    if (!isSupported) {
      alert('Please upload a PDF or image file (.pdf, .png, .jpg, .jpeg, .webp).');
      return;
    }

    const isImage = !fileName.endsWith('.pdf');
    setIsUploading(true);
    setUploadStatus(isImage ? 'Analyzing image with Gemini Vision OCR...' : 'Uploading & extracting document pages...');

    const formData = new FormData();
    formData.append('file', file);

    try {
      setUploadStatus('Chunking & generating fast vector embeddings...');
      const res = await authFetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Upload failed');
      }

      setUploadStatus('Indexing completed!');
      await fetchDocuments();
      await fetchSheetData();

      setTimeout(() => {
        setIsUploading(false);
        setUploadStatus('');
      }, 1000);
    } catch (err) {
      alert(`Error processing file: ${err.message}`);
      setIsUploading(false);
      setUploadStatus('');
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleDeleteDocument = async (docId, filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? All associated vectors and sheet records will be removed.`)) {
      return;
    }

    try {
      const res = await authFetch(`/api/documents/${docId}`, { method: 'DELETE' });
      if (res.ok) {
        if (selectedDocId === docId.toString()) {
          setSelectedDocId('all');
        }
        await fetchDocuments();
        await fetchSheetData();
      } else {
        alert('Failed to delete document.');
      }
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  // Chat message submit with real-time SSE streaming
  const handleSendMessage = async (e) => {
    e?.preventDefault();
    const query = inputQuery.trim();
    if (!query || isGenerating) return;

    setInputQuery('');

    const tempUserMsg = {
      id: Date.now(),
      role: 'user',
      content: query,
      citations: [],
    };
    const assistantMsgId = Date.now() + 1;
    const tempAssistantMsg = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      citations: [],
      streaming: true,
      latency: null,
      model: '',
    };

    setMessages((prev) => [...prev, tempUserMsg, tempAssistantMsg]);
    setIsGenerating(true);

    try {
      const payload = {
        question: query,
        document_id: selectedDocId !== 'all' ? parseInt(selectedDocId) : null,
      };

      const res = await authFetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Streaming connection failed');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let accumulated = '';
      let streamCitations = [];
      let streamLatency = null;
      let streamModel = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop(); // keep last incomplete event

        for (const evt of events) {
          const trimmed = evt.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.replace(/^data:\s*/, '');
          try {
            const data = JSON.parse(jsonStr);
            if (data.type === 'metadata') {
              streamCitations = data.citations || [];
              streamLatency = data.latency || null;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, citations: streamCitations, latency: streamLatency }
                    : m
                )
              );
            } else if (data.type === 'delta') {
              accumulated += data.text;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, content: accumulated } : m
                )
              );
            } else if (data.type === 'done') {
              streamModel = data.model || streamModel;
              if (data.latency) streamLatency = data.latency;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        content: accumulated,
                        citations: streamCitations,
                        latency: streamLatency,
                        model: streamModel,
                        streaming: false,
                      }
                    : m
                )
              );
            } else if (data.type === 'error') {
              accumulated = data.message;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: accumulated, streaming: false }
                    : m
                )
              );
            }
          } catch (jsonErr) {
            console.error('Error parsing event stream:', jsonErr);
          }
        }
      }

      // Ensure streaming indicator is cleared
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId ? { ...m, streaming: false } : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? {
                ...m,
                content: `Error: ${err.message}`,
                citations: [],
                streaming: false,
              }
            : m
        )
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExportMarkdown = () => {
    if (messages.length === 0) return;
    let md = `# AI Document Q&A Chat Export\n`;
    md += `*Exported on ${new Date().toLocaleString()}*\n\n---\n\n`;

    messages.forEach((m) => {
      if (m.role === 'user') {
        md += `### 👤 User:\n${m.content}\n\n`;
      } else {
        md += `### 🤖 Assistant:\n${m.content}\n\n`;
        if (m.citations && m.citations.length > 0) {
          md += `**Sources & Citations:**\n`;
          m.citations.forEach((c) => {
            md += `- **${c.document_name}** (Page ${c.page_number}, Similarity: ${c.score || 'N/A'})\n`;
            md += `  > ${c.snippet.replace(/\n/g, ' ')}\n`;
          });
          md += `\n`;
        }
        if (m.latency) {
          md += `*Latency: ${m.latency.total_ms || 0}ms (${m.latency.retrieval_ms || 0}ms retrieval, ${m.latency.generation_ms || 0}ms generation) | Model: ${m.model || 'Gemini'}*\n\n`;
        }
        md += `---\n\n`;
      }
    });

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_export_${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleClearHistory = async () => {
    if (!window.confirm('Clear all conversation history?')) return;
    try {
      await authFetch('/api/chat/history', { method: 'DELETE' });
      setMessages([]);
    } catch (err) {
      console.error('Error clearing chat history:', err);
    }
  };

  const toggleCitation = (msgId, citIdx) => {
    const key = `${msgId}-${citIdx}`;
    setExpandedCitations((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleExportCSV = async (type) => {
    try {
      const res = await authFetch(`/api/sheets/export-csv?sheet_type=${type}&token=${encodeURIComponent(token || '')}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(`Export failed: ${err.detail || 'Could not export CSV'}`);
        return;
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${type}_export_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('CSV export error:', err);
      alert(`Export failed: ${err.message}`);
    }
  };


  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const activeDocName =
    selectedDocId === 'all'
      ? 'All Uploaded Documents'
      : documents.find((d) => d.id.toString() === selectedDocId)?.filename || 'Selected Document';

  // If unauthenticated, show clean Sign In / Sign Up modal
  if (!token || !user) {
    return (
      <div className="auth-overlay">
        <div className="auth-card">
          <div className="auth-header">
            <div className="auth-logo">
              <BookOpen size={24} />
            </div>
            <h2 className="auth-title">Welcome to DocuRAG</h2>
            <p className="auth-sub">Your personal AI Document Q&A workspace & database</p>
          </div>

          <div className="auth-tab-switch">
            <button
              className={`auth-tab ${authMode === 'login' ? 'active' : ''}`}
              onClick={() => { setAuthMode('login'); setAuthError(''); }}
            >
              Sign In
            </button>
            <button
              className={`auth-tab ${authMode === 'signup' ? 'active' : ''}`}
              onClick={() => { setAuthMode('signup'); setAuthError(''); }}
            >
              Create Account
            </button>
          </div>

          {authError && (
            <div className="auth-error">
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleAuthSubmit}>
            {authMode === 'signup' && (
              <div className="form-group">
                <label className="form-label">Username</label>
                <div className="form-input-wrap">
                  <UserIcon size={15} className="form-input-icon" />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. alex"
                    required
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                  />
                </div>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">{authMode === 'signup' ? 'Email Address' : 'Email or Username'}</label>
              <div className="form-input-wrap">
                <Mail size={15} className="form-input-icon" />
                <input
                  type={authMode === 'signup' ? 'email' : 'text'}
                  className="form-input"
                  placeholder={authMode === 'signup' ? 'alex@example.com' : 'Enter email or username'}
                  required
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <div className="form-input-wrap">
                <Lock size={15} className="form-input-icon" />
                <input
                  type="password"
                  className="form-input"
                  placeholder="••••••••"
                  required
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                />
              </div>
            </div>

            <button type="submit" className="auth-submit-btn" disabled={authLoading}>
              {authLoading ? 'Please wait...' : authMode === 'signup' ? 'Create Free Workspace' : 'Sign In'}
            </button>
          </form>

          {/* Backend Connection & Configuration Panel for Netlify / Remote Host */}
          <div className="auth-server-toggle-wrap">
            <button
              type="button"
              className="auth-server-toggle-btn"
              onClick={() => {
                setTempBackendUrl(backendUrl);
                setShowServerConfig(!showServerConfig);
              }}
            >
              <div className="status-indicator">
                <span className={`status-dot ${isBackendOnline ? 'online' : 'offline'}`} />
                <span className="status-text">
                  {isBackendOnline ? 'Backend API: Connected' : 'Backend API: Offline / Unset'}
                </span>
              </div>
              <div className="toggle-label">
                <Settings size={13} />
                <span>{showServerConfig ? 'Close Settings' : 'Configure API'}</span>
              </div>
            </button>

            {showServerConfig && (
              <div className="auth-server-panel">
                <div className="server-panel-header">
                  <span className="server-panel-title">FastAPI Backend URL</span>
                  {serverSaveSuccess && <span className="server-saved-badge"><Check size={12} /> Saved</span>}
                </div>
                <p className="server-panel-sub">
                  If running on Netlify, specify your deployed backend URL (e.g. Render, Railway, fly.io, or local tunnel).
                </p>
                <div className="form-input-wrap" style={{ marginTop: '0.4rem', marginBottom: '0.5rem' }}>
                  <Server size={14} className="form-input-icon" />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="https://your-backend.onrender.com (or leave empty for default)"
                    value={tempBackendUrl}
                    onChange={(e) => setTempBackendUrl(e.target.value)}
                  />
                </div>
                <div style={{ display: 'flex', gap: '0.4rem', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    className="auth-btn-subtle"
                    onClick={() => {
                      setTempBackendUrl('');
                      saveBackendUrl('');
                    }}
                  >
                    Reset (Default)
                  </button>
                  <button
                    type="button"
                    className="auth-btn-action"
                    onClick={() => saveBackendUrl(tempBackendUrl)}
                  >
                    Save & Test
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Top Header */}
      <header className="app-header">
        <div className="brand">
          <div className="brand-icon">
            <BookOpen size={20} />
          </div>
          <div>
            <h1 className="brand-title">DocuRAG</h1>
            <div className="brand-subtitle">AI Document Q&A & Semantic Database</div>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div className="view-tabs">
          <button
            className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <Sparkles size={15} />
            <span>AI Assistant</span>
          </button>
          <button
            className={`tab-btn ${activeTab === 'sheet' ? 'active' : ''}`}
            onClick={() => { setActiveTab('sheet'); fetchSheetData(); }}
          >
            <Table size={15} />
            <span>Database Sheet</span>
          </button>
        </div>

        {/* Header Right Profile */}
        <div className="header-right">
          {/* Server Connection Badge */}
          <button
            className={`header-server-badge ${isBackendOnline ? 'online' : 'offline'}`}
            onClick={() => {
              setTempBackendUrl(backendUrl);
              setShowServerConfig(true);
            }}
            title="Click to check or configure Backend API"
          >
            <span className={`status-dot ${isBackendOnline ? 'online' : 'offline'}`} />
            <span className="header-server-label">
              {isBackendOnline ? 'Backend Live' : 'Backend Offline'}
            </span>
          </button>

          <div className="user-badge">
            <div className="user-avatar-circle">
              {user.username ? user.username.charAt(0).toUpperCase() : 'U'}
            </div>
            <span>{user.username}</span>
          </div>

          <button className="logout-btn" onClick={handleLogout} title="Sign Out">
            <LogOut size={13} />
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      {activeTab === 'chat' ? (
        /* ================= CHAT ASSISTANT VIEW ================= */
        <div className="app-container">
          {/* Left Sidebar */}
          <aside className="sidebar">
            {/* Upload Area */}
            <div className="sidebar-section">
              <div className="section-title">
                <span>Upload Document</span>
                <FileCheck size={16} />
              </div>

              <div
                className={`dropzone ${dragActive ? 'active' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  accept=".pdf,.png,.jpg,.jpeg,.webp,image/*"
                  onChange={(e) => {
                    if (e.target.files?.[0]) handleFileUpload(e.target.files[0]);
                  }}
                />
                <UploadCloud className="dropzone-icon" />
                <div className="dropzone-text">Click or drag PDF, notes, or bills</div>
                <div className="dropzone-sub">PDFs, bill photos, receipts, scanned notes</div>
              </div>

              {isUploading && (
                <div className="progress-container">
                  <div className="progress-label">
                    <span>{uploadStatus}</span>
                    <RefreshCw size={12} className="spinner" />
                  </div>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill" style={{ width: '85%' }}></div>
                  </div>
                </div>
              )}
            </div>

            {/* Document Scope Filter */}
            <div className="sidebar-section" style={{ paddingBottom: '0.85rem' }}>
              <div className="section-title">
                <span>Query Scope</span>
                <Layers size={15} />
              </div>
              <select
                className="filter-select"
                value={selectedDocId}
                onChange={(e) => setSelectedDocId(e.target.value)}
              >
                <option value="all">Search All Documents ({documents.length})</option>
                {documents.map((doc) => (
                  <option key={doc.id} value={doc.id}>
                    Filter: {doc.filename}
                  </option>
                ))}
              </select>
            </div>

            {/* Document List */}
            <div className="doc-list-container">
              <div className="section-title">
                <span>Your Documents ({documents.length})</span>
                <Database size={15} />
              </div>

              {documents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2.5rem 1rem', color: 'var(--text-muted)' }}>
                  <FileText style={{ width: 40, height: 40, margin: '0 auto 0.5rem', opacity: 0.5 }} />
                  <p style={{ fontSize: '0.82rem', fontWeight: 500, marginBottom: '0.2rem' }}>No documents uploaded</p>
                  <span style={{ fontSize: '0.72rem' }}>Upload your first PDF, note, or bill photo above to start querying.</span>
                </div>
              ) : (
                documents.map((doc) => (
                  <div key={doc.id} className="doc-card">
                    <div className="doc-header">
                      <span className="doc-title">{doc.filename}</span>
                      <button
                        className="doc-delete-btn"
                        title="Delete document and FAISS vectors"
                        onClick={() => handleDeleteDocument(doc.id, doc.filename)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <div className="doc-meta">
                      <span className="doc-tag">{doc.page_count} {doc.page_count === 1 ? 'page' : 'pages'}</span>
                      <span className="doc-tag">{doc.chunk_count} chunks</span>
                      <span className="doc-tag">{formatFileSize(doc.file_size)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </aside>

          {/* Chat Main Area */}
          <main className="chat-area">
            {/* Chat Toolbar */}
            <div className="chat-toolbar">
              <div className="active-filter-indicator">
                <span>Scope:</span>
                <strong>{activeDocName}</strong>
              </div>

              {messages.length > 0 && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="clear-btn" onClick={handleExportMarkdown} title="Export conversation as Markdown (.md)">
                    <Download size={13} />
                    Export Chat (.md)
                  </button>
                  <button className="clear-btn" onClick={handleClearHistory} title="Clear conversation">
                    <Trash2 size={13} />
                    Clear Chat
                  </button>
                </div>
              )}
            </div>

            {/* Messages Container */}
            <div className="messages-container">
              {messages.length === 0 ? (
                <div style={{ textAlign: 'center', marginTop: 'auto', marginBottom: 'auto' }}>
                  <Sparkles style={{ width: 48, height: 48, color: '#4f46e5', margin: '0 auto 1rem' }} />
                  <h3 style={{ color: 'var(--text-main)', marginBottom: '0.5rem', fontWeight: 600 }}>
                    Ready to Answer from Your Documents
                  </h3>
                  <p style={{ maxWidth: 460, margin: '0 auto 1.5rem', fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    Ask any question about your uploaded documents. Answers are synthesized strictly from retrieved passages with exact document and page citations.
                  </p>
                  {documents.length > 0 && (
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                      <button
                        className="clear-btn"
                        style={{ padding: '0.5rem 0.85rem' }}
                        onClick={() => setInputQuery('What are the key findings and conclusions in this document?')}
                      >
                        "What are the key findings and conclusions?"
                      </button>
                      <button
                        className="clear-btn"
                        style={{ padding: '0.5rem 0.85rem' }}
                        onClick={() => setInputQuery('Summarize the main topics and fiscal highlights.')}
                      >
                        "Summarize the main topics and fiscal highlights"
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`message-row ${msg.role}`}>
                    <div className={`avatar ${msg.role}`}>
                      {msg.role === 'user' ? 'U' : <Sparkles size={16} />}
                    </div>
                    <div className="message-bubble">
                      <div style={{ whiteSpace: 'pre-wrap' }}>
                        {msg.content}
                        {msg.streaming && <span className="streaming-cursor">▋</span>}
                      </div>

                      {/* Citations section */}
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="citations-section">
                          <div className="citations-header">
                            <CheckCircle2 size={13} style={{ color: 'var(--success)' }} />
                            <span>Sources & Citations ({msg.citations.length})</span>
                          </div>
                          <div className="citations-grid">
                            {msg.citations.map((citation, citIdx) => {
                              const isExpanded = !!expandedCitations[`${msg.id}-${citIdx}`];
                              return (
                                <div key={citIdx} className="citation-card">
                                  <div
                                    className="citation-top"
                                    onClick={() => toggleCitation(msg.id, citIdx)}
                                  >
                                    <div className="citation-meta">
                                      <span className="citation-badge">{citation.document_name}</span>
                                      <span className="citation-page">Page {citation.page_number}</span>
                                      {citation.score && (
                                        <span className="citation-score">Sim: {citation.score}</span>
                                      )}
                                    </div>
                                    <button className="citation-toggle-btn">
                                      {isExpanded ? (
                                        <>Hide passage <ChevronUp size={14} /></>
                                      ) : (
                                        <>View passage <ChevronDown size={14} /></>
                                      )}
                                    </button>
                                  </div>
                                  {isExpanded && (
                                    <div className="citation-snippet">
                                      {citation.snippet}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Latency Telemetry Badge */}
                      {msg.role === 'assistant' && msg.latency && (
                        <div className="latency-badge" title="RAG Telemetry">
                          <span style={{ color: '#4f46e5', fontWeight: 600 }}>
                            ⚡ {msg.latency.total_ms ? (msg.latency.total_ms / 1000).toFixed(2) + 's total' : 'Fast'}
                          </span>
                          <span>
                            ({msg.latency.retrieval_ms || 0}ms retrieval • {msg.latency.generation_ms ? (msg.latency.generation_ms / 1000).toFixed(2) + 's' : '0s'} generation)
                          </span>
                          {msg.model && (
                            <span className="latency-pill" style={{ marginLeft: 'auto' }}>
                              {msg.model}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}

              {isGenerating && !messages.some((m) => m.streaming && m.content) && (
                <div className="message-row assistant">
                  <div className="avatar assistant">
                    <Sparkles size={16} />
                  </div>
                  <div className="message-bubble" style={{ display: 'inline-block' }}>
                    <div className="typing-indicator">
                      <div className="typing-dot"></div>
                      <div className="typing-dot"></div>
                      <div className="typing-dot"></div>
                      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 6 }}>
                        Searching vectors & synthesizing grounded answer...
                      </span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Bar */}
            <div className="chat-input-wrapper">
              <form onSubmit={handleSendMessage} className="input-box-container">
                <textarea
                  className="chat-textarea"
                  placeholder={
                    documents.length === 0
                      ? 'Upload a PDF on the left to start asking questions...'
                      : 'Ask a question about your documents (e.g. "What is discussed on page 2?")...'
                  }
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  rows={1}
                />
                <button
                  type="submit"
                  className="send-btn"
                  disabled={!inputQuery.trim() || isGenerating}
                  title="Send Question (Enter)"
                >
                  <Send size={16} />
                </button>
              </form>
            </div>
          </main>
        </div>
      ) : (
        /* ================= GOOGLE SHEET DATABASE VIEW ================= */
        <div className="sheet-view-container">
          {/* Top KPI Cards */}
          <div className="sheet-kpi-bar">
            <div className="kpi-card">
              <div className="kpi-icon-wrap indigo">
                <FileText size={20} />
              </div>
              <div>
                <div className="kpi-value">{sheetSummary?.total_documents ?? documents.length}</div>
                <div className="kpi-label">Total Documents</div>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-wrap emerald">
                <Table size={20} />
              </div>
              <div>
                <div className="kpi-value">{sheetSummary?.total_chunks ?? 0}</div>
                <div className="kpi-label">Indexed Chunks</div>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-wrap amber">
                <BookOpen size={20} />
              </div>
              <div>
                <div className="kpi-value">{sheetSummary?.total_pages ?? 0}</div>
                <div className="kpi-label">Total Pages Extracted</div>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-wrap sky">
                <Database size={20} />
              </div>
              <div>
                <div className="kpi-value">{sheetSummary?.total_storage_formatted ?? '0 B'}</div>
                <div className="kpi-label">Storage Allocated</div>
              </div>
            </div>
          </div>

          {/* Sheet Toolbar */}
          <div className="sheet-toolbar">
            <div className="sheet-subtabs">
              <button
                className={`sheet-subtab-btn ${sheetSubTab === 'documents' ? 'active' : ''}`}
                onClick={() => setSheetSubTab('documents')}
              >
                <FileText size={14} />
                <span>Documents Sheet ({sheetDocs.length})</span>
              </button>
              <button
                className={`sheet-subtab-btn ${sheetSubTab === 'chunks' ? 'active' : ''}`}
                onClick={() => setSheetSubTab('chunks')}
              >
                <Layers size={14} />
                <span>Extracted Chunks Sheet ({sheetChunks.length})</span>
              </button>
            </div>

            <div className="sheet-actions">
              {sheetSubTab === 'chunks' && (
                <div className="sheet-search-wrap">
                  <Search size={14} className="sheet-search-icon" />
                  <input
                    type="text"
                    className="sheet-search-input"
                    placeholder="Search chunk text..."
                    value={sheetSearch}
                    onChange={(e) => setSheetSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') fetchSheetData(); }}
                  />
                </div>
              )}

              <button className="sheet-btn" onClick={fetchSheetData} title="Refresh Spreadsheet">
                <RefreshCw size={13} className={sheetLoading ? 'spinner' : ''} />
                <span>Refresh</span>
              </button>

              <button
                className="sheet-btn primary"
                onClick={() => handleExportCSV(sheetSubTab)}
                title="Download CSV spreadsheet"
              >
                <Download size={13} />
                <span>Export to CSV</span>
              </button>
            </div>
          </div>

          {/* Spreadsheet Table Grid */}
          <div className="sheet-grid-wrapper">
            {sheetSubTab === 'documents' ? (
              <table className="sheet-table">
                <thead>
                  <tr>
                    <th className="col-index">#</th>
                    <th>Doc ID</th>
                    <th>Document Filename</th>
                    <th>Pages</th>
                    <th>Chunks</th>
                    <th>File Size</th>
                    <th>Indexing Status</th>
                    <th>Upload Date</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {sheetDocs.length === 0 ? (
                    <tr>
                      <td colSpan="9" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                        No documents indexed in your spreadsheet yet.
                      </td>
                    </tr>
                  ) : (
                    sheetDocs.map((doc, idx) => (
                      <tr key={doc.id}>
                        <td className="col-index">{idx + 1}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{doc.id}</td>
                        <td style={{ fontWeight: 600, color: '#1e293b' }}>{doc.filename}</td>
                        <td>{doc.page_count}</td>
                        <td>{doc.chunk_count}</td>
                        <td>{doc.file_size_formatted}</td>
                        <td>
                          <span style={{ background: '#ecfdf5', color: '#059669', padding: '2px 8px', borderRadius: 4, fontWeight: 500 }}>
                            {doc.status}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-muted)' }}>{doc.created_at}</td>
                        <td>
                          <button
                            className="doc-delete-btn"
                            title="Delete document"
                            onClick={() => handleDeleteDocument(doc.id, doc.filename)}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            ) : (
              <table className="sheet-table">
                <thead>
                  <tr>
                    <th className="col-index">#</th>
                    <th>Chunk ID</th>
                    <th>Document</th>
                    <th>Page #</th>
                    <th>Vector ID</th>
                    <th>Text Passage (Click to inspect)</th>
                    <th>Length</th>
                    <th>Created At</th>
                  </tr>
                </thead>
                <tbody>
                  {sheetChunks.length === 0 ? (
                    <tr>
                      <td colSpan="8" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
                        No chunks found matching your search.
                      </td>
                    </tr>
                  ) : (
                    sheetChunks.map((chunk, idx) => (
                      <tr key={chunk.chunk_id}>
                        <td className="col-index">{idx + 1}</td>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{chunk.chunk_id}</td>
                        <td style={{ fontWeight: 500 }}>{chunk.document_name}</td>
                        <td>
                          <span style={{ background: '#eef2ff', color: '#4f46e5', padding: '2px 6px', borderRadius: 4, fontWeight: 600 }}>
                            Page {chunk.page_number}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{chunk.vector_id}</td>
                        <td
                          className="clickable-cell"
                          title="Click to view full passage"
                          onClick={() => setInspectedCell(chunk)}
                        >
                          {chunk.content_snippet}
                        </td>
                        <td style={{ color: 'var(--text-muted)' }}>{chunk.char_count} chars</td>
                        <td style={{ color: 'var(--text-muted)' }}>{chunk.created_at}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}
          </div>

          {/* Cell Inspection Modal */}
          {inspectedCell && (
            <div className="cell-modal-overlay" onClick={() => setInspectedCell(null)}>
              <div className="cell-modal" onClick={(e) => e.stopPropagation()}>
                <div className="cell-modal-header">
                  <div className="cell-modal-title">
                    Chunk #{inspectedCell.chunk_id} — {inspectedCell.document_name} (Page {inspectedCell.page_number})
                  </div>
                  <button
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                    onClick={() => setInspectedCell(null)}
                  >
                    <X size={18} />
                  </button>
                </div>

                <div className="cell-modal-content">
                  {inspectedCell.full_content}
                </div>

                <div className="cell-modal-footer">
                  <button
                    className="sheet-btn"
                    onClick={() => {
                      navigator.clipboard.writeText(inspectedCell.full_content);
                      alert('Copied passage to clipboard!');
                    }}
                  >
                    <Copy size={13} />
                    <span>Copy Text</span>
                  </button>
                  <button className="sheet-btn primary" onClick={() => setInspectedCell(null)}>
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Backend Server Configuration Modal for Authenticated Session */}
      {showServerConfig && token && (
        <div className="cell-modal-backdrop" onClick={() => setShowServerConfig(false)}>
          <div
            className="cell-modal-card"
            style={{ maxWidth: '480px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="cell-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Server size={18} style={{ color: 'var(--primary-color)' }} />
                <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>Backend API Connection</span>
              </div>
              <button
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                onClick={() => setShowServerConfig(false)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="cell-modal-content" style={{ padding: '1rem', maxHeight: 'none' }}>
              <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '0.85rem', lineHeight: 1.5 }}>
                When running on Netlify, connect your frontend to your deployed FastAPI backend (e.g. Render, Railway, fly.io, or local tunnel).
              </p>

              <div style={{ marginBottom: '1rem' }}>
                <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <span>API Base URL</span>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: isBackendOnline ? '#10b981' : '#f59e0b' }}>
                    {isBackendOnline ? '● Online & Responsive' : '○ Offline / Unreachable'}
                  </span>
                </label>
                <div className="form-input-wrap">
                  <Server size={15} className="form-input-icon" />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="https://your-backend.onrender.com (or empty for default)"
                    value={tempBackendUrl}
                    onChange={(e) => setTempBackendUrl(e.target.value)}
                  />
                </div>
              </div>

              {serverSaveSuccess && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#10b981', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                  <Check size={14} />
                  <span>Settings updated successfully!</span>
                </div>
              )}
            </div>

            <div className="cell-modal-footer" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button
                className="sheet-btn"
                onClick={() => {
                  setTempBackendUrl('');
                  saveBackendUrl('');
                }}
              >
                Reset Default
              </button>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="sheet-btn" onClick={() => setShowServerConfig(false)}>
                  Cancel
                </button>
                <button
                  className="sheet-btn primary"
                  onClick={() => {
                    saveBackendUrl(tempBackendUrl);
                    setTimeout(() => setShowServerConfig(false), 500);
                  }}
                >
                  Save & Reconnect
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
