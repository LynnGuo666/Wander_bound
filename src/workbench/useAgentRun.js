import { useCallback, useRef, useState } from 'react';

function parseFrame(frame) {
  const lines = frame.split('\n');
  const event = lines.find(line => line.startsWith('event: '))?.slice(7);
  const data = lines.filter(line => line.startsWith('data: ')).map(line => line.slice(6)).join('\n');
  if (!event || !data) return null;
  return { event, data: JSON.parse(data) };
}

export function useAgentRun() {
  const [events, setEvents] = useState([]);
  const [plan, setPlan] = useState(null);
  const [question, setQuestion] = useState(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  const controller = useRef(null);
  const sessionId = useRef(null);

  const run = useCallback(async (payload, continuing = false) => {
    if (!continuing) sessionId.current = null;
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setRunning(true); setError('');
    if (!continuing) { setEvents([]); setPlan(null); }
    setQuestion(null);
    let receivedResult = false;
    try {
      const response = await fetch('/api/plan/stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload), signal: current.signal,
      });
      if (!response.ok) {
        const failure = await response.json();
        throw new Error(failure.error || `HTTP ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n');
        let boundary;
        const progress = [];
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const frame = parseFrame(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          if (frame?.event === 'progress') progress.push(frame.data);
          if (frame?.event === 'result') {
            receivedResult = true;
            if (frame.data.question && frame.data.needsInput) {
              sessionId.current = frame.data.sessionId || null;
              setQuestion(frame.data.question);
            } else if (frame.data.error) { sessionId.current = null; setError(frame.data.error); }
            else { sessionId.current = null; setPlan(frame.data); }
          }
        }
        if (progress.length) setEvents(previous => [...previous, ...progress]);
        if (done) break;
      }
      if (!receivedResult) throw new Error('连接已结束，但 Agent 没有返回结果');
    } catch (failure) {
      if (failure.name !== 'AbortError') setError(failure.message || '请求失败');
    } finally {
      if (controller.current === current) { controller.current = null; setRunning(false); }
    }
  }, []);
  const answerQuestion = useCallback((optionId, customText = '') => {
    const option = question?.options?.find(item => item.id === optionId);
    if (!option || !sessionId.current) return;
    run({ sessionId: sessionId.current, answer: { questionId: question.id, optionId, customText: customText.trim() } }, true);
  }, [question, run]);
  const cancel = useCallback(() => controller.current?.abort(), []);
  return { events, plan, question, error, running, run, answerQuestion, cancel };
}
