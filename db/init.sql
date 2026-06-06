-- =============================================================================
-- DB 초기화 SQL (논리 DB: dev)
-- 문제지 제공 스키마 + 성능 최적화(user.email 인덱스).
-- in-cluster Job(db-init.tf) 또는 수동으로 적용. 멱등(재실행 안전).
-- =============================================================================

CREATE DATABASE IF NOT EXISTS dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE dev;

-- user: GET 조회가 email 기준 -> idx_email 인덱스로 풀스캔 방지(0.2초 SLO)
CREATE TABLE IF NOT EXISTS user (
  id       VARCHAR(255) NOT NULL,
  username VARCHAR(255) NOT NULL,
  email    VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username),
  KEY idx_email (email)
);

-- product: GET 조회가 PK(id) 기준 -> 추가 인덱스 불필요
CREATE TABLE IF NOT EXISTS product (
  id         VARCHAR(255) NOT NULL,
  name       VARCHAR(255) NOT NULL,
  price      FLOAT(8)     NOT NULL,
  image_path VARCHAR(500) DEFAULT NULL,
  PRIMARY KEY (id)
);

-- 이미 테이블이 존재(인덱스 없이 생성됨)하는 경우에도 idx_email 보장 (멱등)
SET @idx := (SELECT COUNT(*) FROM information_schema.statistics
             WHERE table_schema = 'dev' AND table_name = 'user' AND index_name = 'idx_email');
SET @ddl := IF(@idx = 0, 'ALTER TABLE user ADD INDEX idx_email (email)', 'DO 0');
PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;