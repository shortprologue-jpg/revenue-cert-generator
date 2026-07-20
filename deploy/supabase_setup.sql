-- ============================================================================
-- BPT 수익화 인증글 생성기 — Supabase 초기 설정 (한 번만)
-- 사용법: Supabase 대시보드 > 왼쪽 "SQL Editor" > 아래를 통째로 붙여넣고 "Run".
-- ============================================================================

-- 1) 인증글 보관함 테이블 -----------------------------------------------------
create table if not exists public.posts (
  id       bigint generated always as identity primary key,
  member   text not null,
  period   text not null,
  revenue  text,
  created  text,                 -- YYYYMMDD 문자열 (사전식 정렬이 곧 시간순)
  body     text,
  unique (member, period)        -- 회원+기간이 같으면 덮어쓰기(upsert on_conflict)
);

alter table public.posts enable row level security;

-- anon(공개) 키로 이 앱이 읽기/쓰기/삭제할 수 있게 허용.
-- ⚠️ 개인용·비민감 데이터 전제 — anon 키를 아는 사람은 이 표를 읽고/쓸 수 있음.
--    회원 매출이 민감하면 Supabase Auth 로그인 기반 정책으로 격상할 것.
drop policy if exists "anon full access on posts" on public.posts;
create policy "anon full access on posts"
  on public.posts for all to anon
  using (true) with check (true);

-- 2) keep-alive 테이블 --------------------------------------------------------
-- GitHub Actions 가 매일 이 표를 select 해서 무료 프로젝트가 7일 방치로
-- 자동정지되는 것을 막는다. 행 1개면 충분.
create table if not exists public.keepalive (
  id bigint generated always as identity primary key
);
insert into public.keepalive default values;

alter table public.keepalive enable row level security;
drop policy if exists "anon select keepalive" on public.keepalive;
create policy "anon select keepalive"
  on public.keepalive for select to anon
  using (true);
