- [ ] Set up nginx and add instructions to README.md, add nginx.conf to repo
- [x] Set up use with Docker


# New workflow
Prerequisite - install Docker. Git is optional.

1. Clone the repository.
    ```bash
    git clone github.com/jwsteens/EquipmentExplorer
    ```
    ```
    # Feedback

    Cloning into 'EquipmentExplorer'...
    remote: Enumerating objects: 364, done.
    remote: Counting objects: 100% (364/364), done.
    remote: Compressing objects: 100% (203/203), done.
    remote: Total 364 (delta 173), reused 342 (delta 155), pack-reused 0 (from 0)
    Receiving objects: 100% (364/364), 422.45 KiB | 1.34 MiB/s, done.
    Resolving deltas: 100% (173/173), done.
    ```
2. Change working directory.
    ```bash
    cd EquipmentExplorer/
    ```
3. Build the Docker image, start the container and start the web server.
    ```bash
    docker compose up -d
    ```
    ```
    # Feedback

    [+] up 2/2
    ✔ Network equipmentexplorer_default Created                                0.0s
    ✔ Container equipment-explorer      Started                                0.2s
    ```
4. Create a terminal inside the Docker container.
    ```bash
    docker compose exec equipment-explorer bash
    ```
    ```
    # Feedback

    root@687d3efc66a7:/app/src#
    ```
5. From this terminal, the guided setup will help you import the cables, documents, document metadata and compartments.
    ```bash
    python manage.py setup
    ```
6. In your web browser, go to localhost:5000 and log in with the default credentials (admin / admin). Go to the Documents page and select the documents you wish to index.
7. In the Docker container terminal, run the following command to index the documents:
    ```bash
    python manage.py index-documents
    ```