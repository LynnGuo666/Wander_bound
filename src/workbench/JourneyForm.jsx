import React from 'react';
import { ArrowRight, Compass, LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';

export default function JourneyForm({ form, update, onSubmit, running }) {
  return <Card>
    <CardHeader><CardTitle className="flex items-center gap-2"><Compass data-icon="inline-start" /> 旅程输入</CardTitle><CardDescription>一句话描述行程，Agent 会按阶段加载工具。</CardDescription></CardHeader>
    <form onSubmit={event => { event.preventDefault(); onSubmit(); }}>
      <CardContent><FieldGroup>
        <Field><FieldLabel htmlFor="trip-query">你想怎么旅行</FieldLabel><Textarea id="trip-query" rows={4} value={form.query} onChange={event => update('query', event.target.value)} placeholder="从上海去深圳玩三天，机票便宜且避开红眼…" /></Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field><FieldLabel htmlFor="trip-origin">出发城市</FieldLabel><Input id="trip-origin" value={form.originCity} onChange={event => update('originCity', event.target.value)} placeholder="上海" /></Field>
          <Field><FieldLabel htmlFor="trip-destination">目的地</FieldLabel><Input id="trip-destination" value={form.destination} onChange={event => update('destination', event.target.value)} placeholder="深圳" required /></Field>
          <Field><FieldLabel htmlFor="trip-date">出发日期</FieldLabel><Input id="trip-date" type="date" value={form.startDate} onChange={event => update('startDate', event.target.value)} required /></Field>
          <Field><FieldLabel htmlFor="trip-days">旅行天数</FieldLabel><NativeSelect id="trip-days" value={form.days} onChange={event => update('days', Number(event.target.value))}>{[1, 2, 3, 4, 5, 6, 7].map(day => <NativeSelectOption key={day} value={day}>{day} 天</NativeSelectOption>)}</NativeSelect></Field>
        </div>
      </FieldGroup></CardContent>
      <CardFooter className="mt-5 justify-between gap-3"><span className="text-xs text-muted-foreground">地点和报价会分别标注来源</span><Button type="submit" disabled={running}>{running ? <LoaderCircle data-icon="inline-start" className="animate-spin" /> : <ArrowRight data-icon="inline-start" />}{running ? '正在执行' : '开始调试'}</Button></CardFooter>
    </form>
  </Card>;
}
