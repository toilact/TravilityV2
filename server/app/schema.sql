CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
  id serial PRIMARY KEY,
  email text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS destinations (
  slug text PRIMARY KEY,
  name text NOT NULL,
  lat double precision NOT NULL,
  lon double precision NOT NULL
);
ALTER TABLE destinations ADD COLUMN IF NOT EXISTS hubs jsonb NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS places (
  id serial PRIMARY KEY,
  ext_id text UNIQUE NOT NULL,
  destination text NOT NULL REFERENCES destinations(slug),
  name text NOT NULL,
  kind text NOT NULL,
  lat double precision NOT NULL,
  lon double precision NOT NULL,
  price integer NOT NULL DEFAULT 0,
  open_hours jsonb NOT NULL DEFAULT '{}',
  outdoor boolean NOT NULL DEFAULT false,
  tags text[] NOT NULL DEFAULT '{}',
  description text NOT NULL DEFAULT '',
  photo_url text,
  embedding vector(768) NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
  id serial PRIMARY KEY,
  user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  spec jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE trips ADD COLUMN IF NOT EXISTS user_messages text[] NOT NULL DEFAULT '{}';
-- change_trip đang chờ người dùng đồng ý ({changes, message, text}); gõ "oke" cũng lập lại được
ALTER TABLE trips ADD COLUMN IF NOT EXISTS pending_replan jsonb;

CREATE TABLE IF NOT EXISTS itineraries (
  id serial PRIMARY KEY,
  trip_id integer NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  version integer NOT NULL,
  data jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (trip_id, version)
);

-- Disruption → Proposal; kiêm log feedback (đã hiện gì, chọn gì) cho ranker (spec revision-giu-muc-dich §5.1)
CREATE TABLE IF NOT EXISTS proposals (
  id serial PRIMARY KEY,
  trip_id integer NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  base_version integer NOT NULL,
  disruption jsonb NOT NULL,
  options jsonb NOT NULL,
  no_feasible text[],
  chosen_index integer,
  applied_version integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Pinned Stop: thuộc Trip, không thuộc version; gán vào stop.pinned khi đọc (spec revision-day-du §2 D2)
ALTER TABLE trips ADD COLUMN IF NOT EXISTS pinned_place_ids integer[] NOT NULL DEFAULT '{}';
