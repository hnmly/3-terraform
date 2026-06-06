###############################################################################
# k8s-secret.tf
# RDS 접속정보를 apps 네임스페이스의 Secret 으로 주입.
# user/product 앱은 envFrom 으로 MYSQL_* 환경변수를 읽음.
###############################################################################

resource "kubernetes_secret" "db" {
  metadata {
    name      = "db-credentials"
    namespace = kubernetes_namespace.apps.metadata[0].name
  }

  data = {
    MYSQL_USER     = var.db_username
    MYSQL_PASSWORD = random_password.db.result
    MYSQL_HOST     = aws_db_instance.main.address
    MYSQL_PORT     = tostring(aws_db_instance.main.port)
    MYSQL_DBNAME   = var.db_name
  }

  type = "Opaque"
}
