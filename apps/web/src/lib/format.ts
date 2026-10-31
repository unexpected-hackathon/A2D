// 화면에 보이는 시각·시간 표기.

// "2026-10-31T14:07:40+09:00" → "10월 31일 오후 2:07"
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'Asia/Seoul',
  }).format(new Date(iso))
}

// 60 → "1시간", 90 → "1시간 30분", 10 → "10분"
export function formatMinutes(min: number): string {
  if (min < 60) return `${min}분`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m ? `${h}시간 ${m}분` : `${h}시간`
}
