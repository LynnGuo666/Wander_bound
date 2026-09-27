import React from 'react';
import { ArrowUpRight, Plane } from 'lucide-react';
import { money } from '../format.mjs';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const shown = value => value === null || value === undefined || value === '' ? '供应商未提供' : String(value);
const dateTime = value => value ? String(value).slice(0, 16).replace('T', ' ') : '供应商未提供';
const yesNo = value => value === true ? '是' : value === false ? '否' : '供应商未提供';
const pieces = value => Number.isFinite(value) ? `${value} 件` : '供应商未提供';
const minuteText = value => Number.isFinite(value) ? `${Math.floor(value / 60)} 小时 ${value % 60} 分` : '供应商未提供';

function rule(value) {
  if (!value || value.allowed === null) return '供应商未提供';
  if (!value.allowed) return '不允许';
  return Number.isFinite(value.penaltyAmount) ? `允许 · 手续费 ${money(value.penaltyAmount, value.penaltyCurrency)}` : '允许 · 手续费未提供';
}

function Detail({ label, value }) {
  return <div className="min-w-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm font-medium">{shown(value)}</dd></div>;
}

function Segment({ segment, index }) {
  const bags = segment.baggage || {};
  const amenities = segment.amenities || {};
  return <section className="border-t py-4 first:border-t-0" aria-label={`第 ${index + 1} 航段`}>
    <h4 className="mb-3 text-sm font-semibold">第 {index + 1} 航段 · {shown(segment.flightNumber)}</h4>
    <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
      <Detail label="营销航司 / 代码" value={[segment.marketingCarrier, segment.marketingCarrierCode].filter(Boolean).join(' · ') || null} />
      <Detail label="实际承运航司 / 代码" value={[segment.operatingCarrier, segment.operatingCarrierCode].filter(Boolean).join(' · ') || null} />
      <Detail label="承运航班号" value={segment.operatingFlightNumber} />
      <Detail label="机型 / 代码" value={[segment.aircraftModel, segment.aircraftCode].filter(Boolean).join(' · ') || null} />
      <Detail label="出发机场 / 航站楼" value={[segment.departureAirport, segment.departureCode, segment.departureTerminal && `${segment.departureTerminal} 航站楼`].filter(Boolean).join(' · ') || null} />
      <Detail label="到达机场 / 航站楼" value={[segment.arrivalAirport, segment.arrivalCode, segment.arrivalTerminal && `${segment.arrivalTerminal} 航站楼`].filter(Boolean).join(' · ') || null} />
      <Detail label="起飞时间" value={dateTime(segment.departureAt)} />
      <Detail label="落地时间" value={dateTime(segment.arrivalAt)} />
      <Detail label="飞行时长" value={minuteText(segment.durationMinutes)} />
      <Detail label="舱位" value={segment.cabinClass} />
      <Detail label="是否含餐" value={yesNo(segment.mealIncluded)} />
      <Detail label="随身 / 托运行李" value={`${pieces(bags.carryOnPieces)} / ${pieces(bags.checkedPieces)}`} />
      <Detail label="行李重量上限" value={Number.isFinite(bags.weightKg) ? `${bags.weightKg} kg` : null} />
      <Detail label="Wi-Fi" value={amenities.wifi === null || amenities.wifi === undefined ? null : `${yesNo(amenities.wifi)}${amenities.wifiCost ? ` · ${amenities.wifiCost}` : ''}`} />
      <Detail label="供电" value={yesNo(amenities.power)} />
      <Detail label="座椅 / 腿部空间" value={[amenities.seatType, amenities.legroom, amenities.seatPitchInches && `${amenities.seatPitchInches} 英寸间距`].filter(Boolean).join(' · ') || null} />
    </dl>
  </section>;
}

export default function FlightResults({ plan }) {
  const flights = [
    ...(plan.flights || []).map(flight => ({ ...flight, direction: '去程', recommended: flight.id === plan.recommendedOutboundFlightId })),
    ...(plan.returnFlights || []).map(flight => ({ ...flight, direction: '返程', recommended: flight.id === plan.recommendedReturnFlightId })),
  ];
  return <Card><CardHeader><CardTitle className="flex items-center gap-2"><Plane /> 航班完整结果</CardTitle><CardDescription>展示本次查询返回的全部去程与返程候选。机型、餐食、行李和退改规则只在供应商明确返回时填写；“供应商未提供”不代表没有该服务。</CardDescription></CardHeader><CardContent>{flights.length ? <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>行程 / 航司</TableHead><TableHead>航司代码 / 航班号</TableHead><TableHead>起降机场与时间</TableHead><TableHead>机型</TableHead><TableHead>含餐</TableHead><TableHead>随身 / 托运</TableHead><TableHead>票价</TableHead></TableRow></TableHeader><TableBody>{flights.map((flight, index) => {
    const first = flight.flightSegments?.[0] || {};
    const bags = first.baggage || flight.baggage || {};
    return <React.Fragment key={`${flight.direction}-${flight.provider}-${flight.id}-${index}`}><TableRow><TableCell className="min-w-32"><span className="font-medium">{flight.direction} · {shown(flight.airline)}</span><div className="mt-1 text-xs text-muted-foreground">{flight.provider}</div>{flight.recommended ? <Badge className="mt-2">推荐</Badge> : null}</TableCell><TableCell className="min-w-32"><strong>{shown(flight.airlineCode)}</strong><div className="mt-1 text-xs text-muted-foreground">{shown(flight.flightNumber)}</div></TableCell><TableCell className="min-w-48"><div>{shown(flight.origin)} → {shown(flight.destination)}</div><div className="mt-1 text-xs text-muted-foreground">{dateTime(flight.departureAt)} → {dateTime(flight.arrivalAt)}</div><div className="mt-1 text-xs text-muted-foreground">{flight.stops === 0 ? '直飞' : `${flight.stops} 次中转`}</div></TableCell><TableCell>{shown(first.aircraftModel)}</TableCell><TableCell>{yesNo(first.mealIncluded ?? flight.mealIncluded)}</TableCell><TableCell className="min-w-32">{pieces(bags.carryOnPieces)} / {pieces(bags.checkedPieces)}</TableCell><TableCell className="min-w-32"><strong>{Number.isFinite(flight.totalPrice) ? money(flight.totalPrice, flight.currency) : '价格未知'}</strong><div className="mt-1 text-xs text-muted-foreground">{flight.priceBasis || '验价以供应商为准'}</div></TableCell></TableRow>
      <TableRow><TableCell colSpan={7} className="bg-muted/30"><details><summary className="cursor-pointer text-sm font-medium text-primary">展开航段、飞机设施、票价与退改明细</summary><div className="mt-3 rounded-md border bg-card px-4">{flight.flightSegments?.length ? flight.flightSegments.map((segment, segmentIndex) => <Segment key={segmentIndex} segment={segment} index={segmentIndex} />) : <p className="py-4 text-sm text-muted-foreground">供应商未提供航段明细。</p>}<dl className="grid gap-x-6 gap-y-4 border-t py-4 sm:grid-cols-2 lg:grid-cols-4"><Detail label="票价产品" value={flight.fareBrand} /><Detail label="基价 / 税费" value={flight.basePrice != null || flight.taxAmount != null ? `${flight.basePrice == null ? '未知' : money(flight.basePrice, flight.currency)} / ${flight.taxAmount == null ? '未知' : money(flight.taxAmount, flight.currency)}` : null} /><Detail label="起飞前改签" value={rule(flight.changePolicy)} /><Detail label="起飞前退票" value={rule(flight.refundPolicy)} /><Detail label="报价有效期" value={flight.expiresAt ? dateTime(flight.expiresAt) : null} /></dl>{flight.bookingUrl ? <a className="mb-4 inline-flex items-center gap-1 text-sm text-primary underline" href={flight.bookingUrl} target="_blank" rel="noreferrer">查看供应商页面 <ArrowUpRight size={14} /></a> : null}</div></details></TableCell></TableRow></React.Fragment>;
  })}</TableBody></Table></div> : <p className="text-sm text-muted-foreground">本次没有可核实的航班结果。</p>}</CardContent></Card>;
}
