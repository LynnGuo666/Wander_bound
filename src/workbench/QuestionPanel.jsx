import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Field, FieldLabel } from '@/components/ui/field';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/components/ui/toast';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

function QuestionChoices({ question, onAnswer, running }) {
  const [selected, setSelected] = useState('');
  const [other, setOther] = useState('');
  return <div className="flex w-full flex-col gap-3 pt-2">
    <p className="font-medium text-foreground">{question.question}</p>
    <ToggleGroup value={selected ? [selected] : []} onValueChange={values => setSelected(values[0] || '')} orientation="vertical" variant="outline" className="w-full">
      {question.options.map(option => <ToggleGroupItem key={option.id} value={option.id} className="h-auto w-full justify-start px-4 py-3 text-left whitespace-normal"><span className="flex flex-col gap-1"><span>{option.label}</span>{option.description ? <span className="text-xs text-muted-foreground">{option.description}</span> : null}</span></ToggleGroupItem>)}
    </ToggleGroup>
    {selected === 'other' ? <Field><FieldLabel htmlFor="question-other">你的答案</FieldLabel><Textarea id="question-other" value={other} onChange={event => setOther(event.target.value)} placeholder="写下你希望的安排…" /></Field> : null}
    <Button className="self-end" disabled={running || !selected || (selected === 'other' && !other.trim())} onClick={() => onAnswer(selected, other)}>继续规划</Button>
  </div>;
}

export default function QuestionPanel({ question, onAnswer, running }) {
  useEffect(() => {
    if (!question) return undefined;
    const id = toast.add({ id: `agent-question-${question.id}`, title: 'Agent 需要你决定',
      description: <QuestionChoices question={question} onAnswer={onAnswer} running={running} />,
      timeout: 0, data: { kind: 'question' } });
    return () => toast.close(id);
  }, [question, onAnswer, running]);
  return null;
}
