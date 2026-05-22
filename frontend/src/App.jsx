import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const API_BASE = 'http://localhost:8000/api/v1'
const metricLabels = {
  wpm: 'WPM',
  fillers: 'Fillers',
  long_pauses: 'Long pauses',
  hesitation: 'Hesitation',
  confidence_score: 'Confidence',
}

const getTimestamp = () => new Date().getTime()
let activeAudio = null

function buildGreeting(interviewType, totalQuestions, candidateName) {
  const namePrefix = candidateName ? `Hi ${candidateName}. ` : 'Hi there. '
  return `${namePrefix}Welcome to your ${interviewType} mock interview. I will ask ${totalQuestions} focused questions based on your resume and the job description. Take a breath, answer naturally, and I will coach you after each response.`
}

function buildReaction(score, feedback) {
  if (score >= 8) return `Nice answer. You scored ${score} out of 10. ${feedback}`
  if (score >= 6) return `Good start. You scored ${score} out of 10. ${feedback}`
  return `Thanks for that answer. You scored ${score} out of 10. ${feedback}`
}

function speakWithBrowserVoice(text) {
  if (!('speechSynthesis' in window) || !text) return Promise.resolve(false)
  window.speechSynthesis.cancel()
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 0.95
    utterance.pitch = 1
    utterance.onend = () => resolve(true)
    utterance.onerror = () => resolve(false)
    window.speechSynthesis.speak(utterance)
  })
}

async function speak(text, onEngineChange) {
  if (!text) return

  try {
    window.speechSynthesis?.cancel()
    activeAudio?.pause()
    activeAudio = null

    const response = await fetch(`${API_BASE}/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!response.ok) throw new Error('Kokoro unavailable')

    const audioUrl = URL.createObjectURL(await response.blob())
    const audio = new Audio(audioUrl)
    activeAudio = audio
    onEngineChange?.('Kokoro')
    await new Promise((resolve, reject) => {
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl)
        resolve()
      }
      audio.onerror = reject
      audio.play().catch(reject)
    })
  } catch {
    if (await speakWithBrowserVoice(text)) onEngineChange?.('Browser fallback')
    else onEngineChange?.('No voice available')
  }
}

function App() {
  const [interviewType, setInterviewType] = useState('hr')
  const [resumeText, setResumeText] = useState('')
  const [jdText, setJdText] = useState('')
  const [resumeFile, setResumeFile] = useState(null)
  const [jdFile, setJdFile] = useState(null)
  const [sessionId, setSessionId] = useState('')
  const [question, setQuestion] = useState('')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [totalQuestions, setTotalQuestions] = useState(0)
  const [answer, setAnswer] = useState('')
  const [messages, setMessages] = useState([])
  const [feedbackLog, setFeedbackLog] = useState([])
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [answerStartedAt, setAnswerStartedAt] = useState(null)
  const [longPauseCount, setLongPauseCount] = useState(0)
  const [speechConfidence, setSpeechConfidence] = useState(null)
  const [voiceEngine, setVoiceEngine] = useState('Kokoro preferred')
  const [sttStatus, setSttStatus] = useState('Whisper STT ready')
  const [waveLevel, setWaveLevel] = useState(0)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const mediaStreamRef = useRef(null)
  const audioContextRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const shouldSubmitRecordingRef = useRef(false)
  const lastSpeechAtRef = useRef(null)
  const chatEndRef = useRef(null)
  const answerRef = useRef('')

  const canStart = useMemo(
    () => Boolean((resumeFile || resumeText.trim()) && (jdFile || jdText.trim())),
    [resumeFile, resumeText, jdFile, jdText],
  )
  const voiceAvailable = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder)
  const interviewActive = Boolean(sessionId && question && question !== 'Interview completed')

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, feedbackLog])

  useEffect(() => {
    fetch(`${API_BASE}/voice/warmup`, { method: 'POST' }).catch(() => {
      setVoiceEngine('Kokoro warmup pending')
    })
  }, [])

  const prepareQuestion = (nextQuestion) => {
    setQuestion(nextQuestion)
    setAnswerStartedAt(getTimestamp())
    setLongPauseCount(0)
    setSpeechConfidence(null)
  }

  const startSession = async () => {
    setLoading(true)
    setError('')
    setReport(null)
    setFeedbackLog([])
    setMessages([])
    setSessionId('')

    try {
      const formData = new FormData()
      formData.append('interview_type', interviewType)
      if (resumeFile) formData.append('resume_file', resumeFile)
      else formData.append('resume_text', resumeText)
      if (jdFile) formData.append('jd_file', jdFile)
      else formData.append('jd_text', jdText)

      const res = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error(await readApiError(res, 'Failed to start session'))
      const data = await res.json()
      const greeting = buildGreeting(interviewType, data.total_questions, data.candidate_name)
      setSessionId(data.session_id)
      setQuestion(greeting)
      setQuestionIndex(1)
      setTotalQuestions(data.total_questions)
      setMessages([{ role: 'coach', text: greeting }])
      setLoading(false)
      await speak(greeting, setVoiceEngine)
      prepareQuestion(data.first_question)
      setMessages((prev) => [...prev, { role: 'coach', text: data.first_question }])
      await speak(data.first_question, setVoiceEngine)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const submitAnswer = async (answerOverride = answerRef.current) => {
    const submittedAnswer = answerOverride.trim()
    if (!submittedAnswer || !interviewActive) return
    setLoading(true)
    setError('')
    stopRecording()

    const durationSeconds = answerStartedAt ? Math.max((getTimestamp() - answerStartedAt) / 1000, 1) : null
    const submittedQuestion = question

    try {
      setMessages((prev) => [...prev, { role: 'candidate', text: submittedAnswer }])
      const res = await fetch(`${API_BASE}/sessions/${sessionId}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answer: submittedAnswer,
          duration_seconds: durationSeconds,
          long_pause_count: longPauseCount,
          speech_confidence: speechConfidence,
        }),
      })
      if (!res.ok) throw new Error(await readApiError(res, 'Failed to submit answer'))
      const data = await res.json()
      setFeedbackLog((prev) => [
        ...prev,
        {
          question: submittedQuestion,
          answer: submittedAnswer,
          score: data.score,
          feedback: data.feedback,
          metrics: data.metrics,
        },
      ])
      setAnswer('')
      answerRef.current = ''

      if (data.done) {
        const doneMessage = `${buildReaction(data.score, data.feedback)} Interview completed. I prepared your final coaching report below.`
        setQuestion('Interview completed')
        setMessages((prev) => [...prev, { role: 'coach', text: doneMessage }])
        void speak(doneMessage, setVoiceEngine)
        await fetchReport(sessionId)
      } else {
        const reaction = buildReaction(data.score, data.feedback)
        const nextPrompt = `${reaction} Next question: ${data.next_question}`
        prepareQuestion(data.next_question)
        setQuestionIndex(data.question_index + 1)
        setMessages((prev) => [...prev, { role: 'coach', text: nextPrompt }])
        await speak(nextPrompt, setVoiceEngine)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchReport = async (id) => {
    const res = await fetch(`${API_BASE}/sessions/${id}/report`)
    if (!res.ok) throw new Error(await readApiError(res, 'Failed to fetch report'))
    const data = await res.json()
    setReport(data)
  }

  const startSilenceTracking = (stream) => {
    const AudioContext = window.AudioContext || window.webkitAudioContext
    if (!AudioContext) return

    const context = new AudioContext()
    const analyser = context.createAnalyser()
    const source = context.createMediaStreamSource(stream)
    const data = new Uint8Array(analyser.fftSize)
    source.connect(analyser)
    audioContextRef.current = context
    lastSpeechAtRef.current = getTimestamp()

    const tick = () => {
      if (!mediaRecorderRef.current) return

      analyser.getByteTimeDomainData(data)
      const volume = data.reduce((sum, value) => sum + Math.abs(value - 128), 0) / data.length
      const now = getTimestamp()
      setWaveLevel(Math.min(1, volume / 24))

      if (volume > 5) {
        if (lastSpeechAtRef.current && now - lastSpeechAtRef.current > 2500) {
          setLongPauseCount((count) => count + 1)
        }
        lastSpeechAtRef.current = now
      }

      silenceTimerRef.current = window.setTimeout(tick, 200)
    }

    tick()
  }

  const startRecording = async () => {
    if (!voiceAvailable || isRecording) return
    setError('')
    setSttStatus('Listening with browser mic')

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      mediaStreamRef.current = stream
      mediaRecorderRef.current = recorder
      audioChunksRef.current = []
      setAnswerStartedAt(getTimestamp())
      setSpeechConfidence(0.85)
      setIsRecording(true)
      startSilenceTracking(stream)

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data)
      }

      recorder.onstop = () => {
        if (shouldSubmitRecordingRef.current) {
          shouldSubmitRecordingRef.current = false
          void transcribeAndSubmit()
        }
      }

      recorder.start()
    } catch (event) {
      setIsRecording(false)
      setSttStatus('Mic unavailable')
      setError(`Could not access microphone: ${event.message}`)
    }
  }

  const stopRecording = ({ submit = false } = {}) => {
    shouldSubmitRecordingRef.current = submit
    window.clearTimeout(silenceTimerRef.current)
    setWaveLevel(0)
    audioContextRef.current?.close()
    audioContextRef.current = null

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
    mediaStreamRef.current = null
    setIsRecording(false)

    if (!submit) {
      mediaRecorderRef.current = null
      audioChunksRef.current = []
    }
  }

  const transcribeAndSubmit = async () => {
    const mimeType = mediaRecorderRef.current?.mimeType || 'audio/webm'
    const audioBlob = new Blob(audioChunksRef.current, { type: mimeType })
    mediaRecorderRef.current = null

    if (!audioBlob.size) {
      setError('No audio was captured. Please try again.')
      setSttStatus('Whisper STT ready')
      return
    }

    setLoading(true)
    setSttStatus('Transcribing with Whisper')
    try {
      const formData = new FormData()
      formData.append('audio_file', audioBlob, 'answer.webm')
      const res = await fetch(`${API_BASE}/voice/stt`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error(await readApiError(res, 'Failed to transcribe audio'))
      const data = await res.json()
      const transcript = data.text.trim()
      setAnswer(transcript)
      answerRef.current = transcript
      setSttStatus('Transcript ready')
      await submitAnswer(transcript)
    } catch (event) {
      setError(event.message)
      setSttStatus('Whisper STT failed')
    } finally {
      setLoading(false)
      audioChunksRef.current = []
    }
  }

  const toggleDictation = () => {
    if (isRecording) {
      stopRecording({ submit: true })
      return
    }

    setAnswer('')
    answerRef.current = ''
    startRecording()
  }

  const resetInterview = () => {
    stopRecording()
    activeAudio?.pause()
    activeAudio = null
    window.speechSynthesis?.cancel()
    setSessionId('')
    setQuestion('')
    setQuestionIndex(0)
    setTotalQuestions(0)
    setAnswer('')
    answerRef.current = ''
    setMessages([])
    setFeedbackLog([])
    setReport(null)
    setError('')
  }

  return (
    <div className="app">
      {loading && !sessionId && (
        <div className="loading-overlay" role="status" aria-live="polite">
          <div className="loading-card">
            <div className="loading-orb" />
            <h2>Preparing your interview</h2>
            <p>Reading your resume and JD, then generating tailored questions with Groq.</p>
          </div>
        </div>
      )}

      <header className="hero">
        <div className="eyebrow">AI mock interviews with delivery analytics</div>
        <h1>CommCoach AI</h1>
        <p>
          Upload a resume and job description, start a guided interview, answer naturally, and get
          coaching on content, pace, pauses, confidence, fillers, and grammar.
        </p>
      </header>

      <main className="workspace">
        <section className="setup-panel">
          <div className="panel-heading">
            <span>01</span>
            <div>
              <h2>Setup</h2>
              <p>PDF upload is preferred; paste text if you want a quick dry run.</p>
            </div>
          </div>

          <label>Interview Type</label>
          <select value={interviewType} onChange={(e) => setInterviewType(e.target.value)}>
            <option value="hr">HR</option>
            <option value="technical">Technical</option>
            <option value="managerial">Managerial</option>
            <option value="behavioral">Behavioral</option>
          </select>

          <div className="upload-grid">
            <FileDrop
              label="Resume PDF"
              file={resumeFile}
              onChange={setResumeFile}
              helper="Upload your resume or paste it below."
            />
            <FileDrop
              label="Job Description PDF"
              file={jdFile}
              onChange={setJdFile}
              helper="Upload the JD or paste it below."
            />
          </div>

          <label>Resume Text</label>
          <textarea
            rows={5}
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            placeholder="Paste resume text here if you are not uploading a PDF."
          />

          <label>Job Description Text</label>
          <textarea
            rows={5}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="Paste the role description, requirements, and expectations."
          />

          <div className="actions">
            <button className="primary" disabled={!canStart || loading} onClick={startSession}>
              {loading && !sessionId ? 'Preparing interview...' : 'Start Interview'}
            </button>
            {sessionId && (
              <button className="ghost" onClick={resetInterview}>
                Reset
              </button>
            )}
          </div>

          {!voiceAvailable && (
            <p className="hint">
              Browser audio recording is not available here. Please use a modern Chromium browser.
            </p>
          )}
          <p className="hint">Voice engine: {voiceEngine}. Kokoro is tried first, browser TTS is only the fallback.</p>
          <p className="hint">STT engine: {sttStatus}. Audio is sent to the backend Whisper pipeline.</p>
        </section>

        <section className="interview-panel">
          <div className="panel-heading">
            <span>02</span>
            <div>
              <h2>Interview Room</h2>
              <p>
                {sessionId
                  ? `Question ${Math.min(questionIndex, totalQuestions)} of ${totalQuestions}`
                  : 'Your conversational interview appears here.'}
              </p>
            </div>
          </div>

          <div className="chat-window">
            {messages.length === 0 && (
              <div className="empty-state">
                <div className="orb" />
                <h3>Ready when you are.</h3>
                <p>Start the interview and I will ask one focused question at a time.</p>
              </div>
            )}
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <span>{message.role === 'coach' ? 'Coach' : 'You'}</span>
                <p>{message.text}</p>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="answer-box">
            <div className="transcript-box" aria-live="polite">
              {answer || (interviewActive ? 'Click Start Listening and answer out loud. Your transcript will appear here.' : 'Start an interview to answer by voice.')}
            </div>
            <div className={`recorder-visualizer ${isRecording ? 'active' : ''}`} aria-hidden="true">
              {Array.from({ length: 21 }, (_, index) => {
                const centerDistance = Math.abs(index - 10)
                const height = 18 + waveLevel * (76 - centerDistance * 4)
                return <span key={index} style={{ height: `${Math.max(14, height)}px` }} />
              })}
            </div>
            <div className="answer-toolbar">
              <button
                className={isRecording ? 'danger' : 'secondary'}
                disabled={!interviewActive || !voiceAvailable || (loading && !isRecording)}
                onClick={toggleDictation}
              >
                {isRecording ? 'Stop and Analyze' : 'Start Listening'}
              </button>
            </div>
            <div className="live-stats">
              <span>{isRecording ? 'Listening now' : 'Mic idle'}</span>
              <span>Long pauses: {longPauseCount}</span>
            </div>
          </div>
        </section>
      </main>

      {feedbackLog.length > 0 && (
        <section className="feedback-panel">
          <div className="panel-heading">
            <span>03</span>
            <div>
              <h2>Live Coaching</h2>
              <p>Each response gets scored for substance and delivery.</p>
            </div>
          </div>

          <div className="feedback-grid">
            {feedbackLog.map((item, idx) => (
              <article key={idx} className="feedback-card">
                <div className="score-pill">{item.score}/10</div>
                <h3>{item.question}</h3>
                <p>{item.feedback}</p>
                <div className="metric-grid">
                  {Object.entries(metricLabels).map(([key, label]) => (
                    <div key={key}>
                      <span>{label}</span>
                      <strong>
                        {key === 'confidence_score' ? `${item.metrics[key]}%` : item.metrics[key]}
                      </strong>
                    </div>
                  ))}
                </div>
                <div className="grammar-note">
                  <span>Grammar</span>
                  <p>{item.metrics.grammar}</p>
                </div>
                <ul>
                  {item.metrics.suggestions.map((suggestion) => (
                    <li key={suggestion}>{suggestion}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>
      )}

      {report && (
        <section className="report-panel">
          <div>
            <span className="report-kicker">Final report</span>
            <h2>{report.average_score}/10 average score</h2>
          </div>
          <ReportColumn title="Strengths" items={report.strengths} />
          <ReportColumn title="Improve" items={report.improvements} />
          <ReportColumn title="Practice Plan" items={report.plan} />
        </section>
      )}

      {error && <p className="error">{error}</p>}
    </div>
  )
}

function FileDrop({ label, file, helper, onChange }) {
  return (
    <label className="file-drop">
      <span>{label}</span>
      <strong>{file ? file.name : 'Choose PDF or TXT'}</strong>
      <small>{helper}</small>
      <input
        type="file"
        accept=".pdf,.txt"
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
    </label>
  )
}

function ReportColumn({ title, items }) {
  return (
    <div className="report-column">
      <h3>{title}</h3>
      {items.map((item) => (
        <p key={item}>{item}</p>
      ))}
    </div>
  )
}

async function readApiError(response, fallback) {
  try {
    const data = await response.json()
    return data.detail || fallback
  } catch {
    return fallback
  }
}

export default App
