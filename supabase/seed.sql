-- =============================================================================
-- なみログ seed: factor_catalog 12 行（ARCHITECTURE.md §2.5）
--   factor_key は不変の論理キー（P-3）。ラベルや順序は変えてもキーは変えない。
--   `supabase db reset` で migrations 適用後に投入される。冪等にするため upsert。
-- =============================================================================
insert into public.factor_catalog (factor_key, label, input_type, unit, description, sort_order) values
  ('barometric_pressure', '気圧（低下傾向）',            'open_meteo', 'hPa',   '気圧の低下傾向。前日比の差分も算出。', 1),
  ('sunshine_hours',      '日照時間',                    'open_meteo', 'hours', '1日の日照時間（秒→時間換算）。',      2),
  ('temperature_swing',   '気温・寒暖差',                'open_meteo', '℃',    '最高気温と最低気温の差（寒暖差）。',   3),
  ('weather_humidity',    '天候・湿度',                  'open_meteo', '%',     '天候コードと湿度の代表値。',           4),
  ('season_daylength',    '季節・日長の変化',            'derived',    'hours', '日付と緯度から算出する日長・季節位相。', 5),
  ('sleep',               '睡眠時間・就寝起床リズム',    'manual',     'hours', '睡眠時間・就寝/起床リズム（手入力）。', 6),
  ('menstrual_cycle',     '月経周期',                    'manual',     'day',   '月経周期の位相（手入力）。',           7),
  ('medication',          '服薬状況（飲み忘れ）',        'manual',     null,    '服薬の有無・飲み忘れ（手入力）。',     8),
  ('activity_steps',      '運動量・歩数',                'manual',     'steps', '運動量・歩数（手入力）。',             9),
  ('caffeine_alcohol',    'カフェイン・アルコール摂取',  'manual',     null,    'カフェイン/アルコール摂取（手入力）。', 10),
  ('schedule_density',    '予定の密度（社会的リズム）',  'manual',     null,    '予定の密度・社会的リズム（手入力）。', 11),
  ('stress_event',        '対人・ストレスイベント',      'manual',     null,    '対人・ストレスイベント（手入力）。',   12)
on conflict (factor_key) do update
  set label = excluded.label,
      input_type = excluded.input_type,
      unit = excluded.unit,
      description = excluded.description,
      sort_order = excluded.sort_order;
