"""The citation URL is a redirector: browsers to /app, everyone else to /api/v1."""

BROWSER = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def test_browser_goes_to_the_reader(client):
    response = client.get("/us/pl/81/740/s3", headers={"Accept": BROWSER}, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app/us/pl/81/740/s3"
    assert response.headers["vary"] == "Accept"


def test_a_program_goes_to_the_api(client):
    response = client.get("/us/act/1950-08-30/ch823/s3", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/api/v1/us/act/1950-08-30/ch823/s3"


def test_format_wins_and_the_query_survives(client):
    response = client.get(
        "/us/sComp/83/703/tI/ch1./s1?format=json&through=118-67",
        headers={"Accept": BROWSER},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "/api/v1/us/sComp/83/703/tI/ch1./s1?format=json&through=118-67"


def test_stat_pages_redirect_too(client):
    response = client.get("/us/stat/64/564", follow_redirects=False)
    assert response.headers["location"] == "/api/v1/us/stat/64/564"


def test_a_browsers_404_goes_to_the_reader(client):
    response = client.get("/about?x=1", headers={"Accept": BROWSER}, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app/about?x=1"
    assert client.get("/nothing-here", headers={"Accept": BROWSER}, follow_redirects=False).headers["location"] == "/app/nothing-here"


def test_a_404_stays_json_for_the_api_and_for_programs(client):
    assert client.get("/nothing-here", follow_redirects=False).json() == {"detail": "Not Found"}
    for path in ("/api/v1/nothing", "/api/nothing", "/app/nothing"):
        response = client.get(path, headers={"Accept": BROWSER}, follow_redirects=False)
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}
    response = client.post("/nothing-here", headers={"Accept": BROWSER}, follow_redirects=False)
    assert response.status_code == 404


def test_an_api_404_with_a_detail_is_unchanged(client):
    response = client.get("/api/v1/us/pl/99/99999", headers={"Accept": BROWSER})
    assert response.status_code == 404
    assert "nothing at /us/pl/99/99999" in response.json()["detail"]
