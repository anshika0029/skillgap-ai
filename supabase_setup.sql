-- Run once in Supabase -> SQL Editor
create table if not exists profiles (
  username text primary key,
  data jsonb not null
);
alter table profiles enable row level security;
