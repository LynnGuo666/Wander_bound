import React, { useState } from 'react';
import { MessageCircleQuestion } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

export default function QuestionPanel({ question, onAnswer, running }) {
  const [selected, setSelected] = useState('');
  const [other, setOther] = useState('');
  if (!question) return null;
  return <Card className="border-primary/40"><CardHeader><CardTitle className="flex items-center gap-2"><MessageCircleQuestion /> Agent 需要你决定</CardTitle><CardDescription>{question.question}</CardDescription></CardHeader><CardContent className="grid gap-2">{question.options.map(option => <button key={option.id} type="button" onClick={() => setSelected(option.id)} aria-pressed={selected === option.id}
    className={`rounded-md border px-4 py-3 text-left text-sm transition-colors hover:border-primary ${selected === option.id ? 'border-primary bg-primary/5' : 'border-border'}`}>
    <span className="font-medium">{option.label}</span>{option.description ? <span className="mt-1 block text-xs text-muted-foreground">{option.description}</span> : null}
  </button>)}{selected === 'other' ? <Textarea value={other} onChange={event => setOther(event.target.value)} placeholder="写下你希望的安排…" aria-label="其他答案" /> : null}</CardContent><CardFooter><Button disabled={running || !selected || (selected === 'other' && !other.trim())} onClick={() => onAnswer(selected, other)}>按这个答案继续规划</Button></CardFooter></Card>;
}
