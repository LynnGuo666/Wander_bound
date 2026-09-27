import React, { useEffect, useState } from 'react';
import { MessageCircleQuestion } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, FieldLabel } from '@/components/ui/field';
import { Textarea } from '@/components/ui/textarea';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

export default function QuestionPanel({ question, onAnswer, running }) {
  const [selected, setSelected] = useState('');
  const [other, setOther] = useState('');
  useEffect(() => { setSelected(''); setOther(''); }, [question?.id]);
  if (!question) return null;
  return <aside role="region" aria-live="polite" aria-label="Agent 提问" className="fixed inset-x-4 bottom-4 mx-auto max-h-[70vh] max-w-2xl overflow-y-auto"><Card className="border-primary shadow-xl"><CardHeader><CardTitle className="flex items-center gap-2"><MessageCircleQuestion data-icon="inline-start" /> Agent 需要你决定</CardTitle><CardDescription>{question.question}</CardDescription></CardHeader><CardContent className="flex flex-col gap-3"><ToggleGroup value={selected ? [selected] : []} onValueChange={values => setSelected(values[0] || '')} orientation="vertical" variant="outline" className="w-full">{question.options.map(option => <ToggleGroupItem key={option.id} value={option.id} className="h-auto w-full justify-start px-4 py-3 text-left whitespace-normal"><span className="flex flex-col gap-1"><span>{option.label}</span>{option.description ? <span className="text-xs text-muted-foreground">{option.description}</span> : null}</span></ToggleGroupItem>)}</ToggleGroup>{selected === 'other' ? <Field><FieldLabel htmlFor="question-other">你的答案</FieldLabel><Textarea id="question-other" value={other} onChange={event => setOther(event.target.value)} placeholder="写下你希望的安排…" /></Field> : null}</CardContent><CardFooter className="justify-end"><Button disabled={running || !selected || (selected === 'other' && !other.trim())} onClick={() => onAnswer(selected, other)}>继续规划</Button></CardFooter></Card></aside>;
}
