###############################################################################
# db-init.tf
# DB 테이블 생성 자동화 (RDS 가 private 이므로 클러스터 내부 Job 으로 실행)
#   - db/init.sql 을 ConfigMap 으로 마운트
#   - mysql:8 클라이언트 Job 이 db-credentials Secret 으로 접속해 init.sql 실행
#   - CREATE TABLE IF NOT EXISTS 라 재실행해도 안전(멱등)
#   - apply 는 Job 완료까지 대기
###############################################################################

resource "kubernetes_config_map_v1" "db_init" {
  metadata {
    name      = "db-init-sql"
    namespace = kubernetes_namespace.apps.metadata[0].name
  }

  data = {
    "init.sql" = file("${path.module}/../db/init.sql")
  }
}

resource "kubernetes_job_v1" "db_init" {
  metadata {
    name      = "db-init"
    namespace = kubernetes_namespace.apps.metadata[0].name
  }

  spec {
    backoff_limit = 4

    template {
      metadata {
        labels = { job = "db-init" }
      }
      spec {
        restart_policy = "OnFailure"

        container {
          name    = "db-init"
          image   = "mysql:8"
          command = ["sh", "-c", "mysql -h \"$MYSQL_HOST\" -P \"$MYSQL_PORT\" -u \"$MYSQL_USER\" \"$MYSQL_DBNAME\" < /sql/init.sql"]

          # mysql 클라이언트는 MYSQL_PWD 환경변수로 비밀번호를 읽음
          env {
            name = "MYSQL_PWD"
            value_from {
              secret_key_ref {
                name = "db-credentials"
                key  = "MYSQL_PASSWORD"
              }
            }
          }

          # MYSQL_HOST/PORT/USER/DBNAME 주입
          env_from {
            secret_ref {
              name = "db-credentials"
            }
          }

          volume_mount {
            name       = "sql"
            mount_path = "/sql"
          }
        }

        volume {
          name = "sql"
          config_map {
            name = kubernetes_config_map_v1.db_init.metadata[0].name
          }
        }
      }
    }
  }

  wait_for_completion = true

  timeouts {
    create = "5m"
    update = "5m"
  }

  depends_on = [
    kubernetes_secret.db,
    aws_db_instance.main,
  ]
}