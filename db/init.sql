-- =============================================================================
-- DB 초기화 SQL (논리 DB: dev)
-- 문제지 제공 스키마. load_user.dump 적용 전 테이블 생성에 사용.
-- 적용: mysql -h <MYSQL_HOST> -u <MYSQL_USER> -p dev < init.sql
-- =============================================================================

CREATE DATABASE IF NOT EXISTS dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE dev;

CREATE TABLE IF NOT EXISTS user (
  id       VARCHAR(255) NOT NULL,
  username VARCHAR(255) NOT NULL,
  email    VARCHAR(255) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_username (username)
);

CREATE TABLE IF NOT EXISTS product (
  id         VARCHAR(255) NOT NULL,
  name       VARCHAR(255) NOT NULL,
  price      FLOAT(8)     NOT NULL,
  image_path VARCHAR(500) DEFAULT NULL,
  PRIMARY KEY (id)
);

-- 성능 효율성 참고: product 는 동일 id 조회가 빈번 -> PK(id) 조회로 최적.
-- user 는 email 로 GET 조회 -> 필요 시 email 인덱스 추가 검토.
-- ALTER TABLE user ADD INDEX idx_email (email);
