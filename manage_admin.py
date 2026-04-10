from __future__ import annotations

from app.services.auth_service import AuthService


DB_PATH = "data/chamados.db"


def ask(prompt: str) -> str:
    return input(prompt).strip()


def print_menu() -> None:
    print("\n=== Gestao de Contas Administradoras ===")
    print("1) Listar contas")
    print("2) Criar conta / redefinir senha")
    print("3) Alterar login")
    print("4) Alterar senha")
    print("5) Remover conta")
    print("0) Sair")


def main() -> None:
    auth = AuthService(DB_PATH)

    while True:
        print_menu()
        choice = ask("Escolha uma opcao: ")

        if choice == "0":
            print("Saindo.")
            return

        if choice == "1":
            users = auth.list_admin_usernames()
            if not users:
                print("Nenhuma conta encontrada.")
            else:
                print("Contas:")
                for user in users:
                    print(f"- {user}")
            continue

        if choice == "2":
            username = ask("Login: ")
            password = ask("Senha: ")
            try:
                auth.create_or_update_admin(username, password)
                print(f"Conta '{username}' salva com sucesso.")
            except ValueError as exc:
                print(f"Erro: {exc}")
            continue

        if choice == "3":
            old_username = ask("Login atual: ")
            new_username = ask("Novo login: ")
            try:
                changed = auth.rename_admin(old_username, new_username)
                if changed:
                    print("Login alterado com sucesso.")
                else:
                    print("Conta nao encontrada.")
            except ValueError as exc:
                print(f"Erro: {exc}")
            continue

        if choice == "4":
            username = ask("Login: ")
            new_password = ask("Nova senha: ")
            try:
                changed = auth.update_password(username, new_password)
                if changed:
                    print("Senha alterada com sucesso.")
                else:
                    print("Conta nao encontrada.")
            except ValueError as exc:
                print(f"Erro: {exc}")
            continue

        if choice == "5":
            users = auth.list_admin_usernames()
            if len(users) <= 1:
                print("Operacao bloqueada: mantenha ao menos 1 conta administradora.")
                continue

            username = ask("Login para remover: ")
            confirm = ask(f"Confirmar remocao de '{username}'? (s/N): ").lower()
            if confirm != "s":
                print("Remocao cancelada.")
                continue

            try:
                deleted = auth.delete_admin(username)
                if deleted:
                    print("Conta removida com sucesso.")
                else:
                    print("Conta nao encontrada.")
            except ValueError as exc:
                print(f"Erro: {exc}")
            continue

        print("Opcao invalida.")


if __name__ == "__main__":
    main()
