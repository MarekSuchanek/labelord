import pytest
from labelord.github import GitHub, GitHubError

LABELORD_REPO = 'MarekSuchanek/labelord'
UNEXISTING_REPO = 'MarekSuchanek/adsw51dwa1d5123aa'


def test_list_repositories(github):
    repositories = github.list_repositories()

    assert len(repositories) == 49
    assert LABELORD_REPO in repositories


def test_list_repositories_with_bad_token(github_bad_token):
    with pytest.raises(GitHubError) as err:
        github_bad_token.list_repositories()

    assert err.value.status_code == 401
    assert err.value.message == 'Bad credentials'


def test_list_labels_from_existing_repo(github):
    labels = github.list_labels(LABELORD_REPO)

    assert len(labels) == 8
    assert labels['bug'] == 'ee0701'


def test_list_labels_from_unexisting_repo(github):
    with pytest.raises(GitHubError) as err:
        github.list_labels(UNEXISTING_REPO)

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'


def test_list_labels_with_bad_token(github_bad_token):
    with pytest.raises(GitHubError) as err:
        github_bad_token.list_labels(LABELORD_REPO)

    assert err.value.status_code == 401
    assert err.value.message == 'Bad credentials'


def test_create_label_for_existing_repo(github):
    # Just matching with betamax
    github.create_label(LABELORD_REPO, 'Testing', 'aaaaaa')


def test_create_label_that_already_exists(github):
    with pytest.raises(GitHubError) as err:
        github.create_label(LABELORD_REPO, 'Testing', 'aaaaaa')

    assert err.value.status_code == 422
    assert err.value.message == 'Validation Failed'


def test_create_label_with_weird_color(github):
    with pytest.raises(GitHubError) as err:
        github.create_label(LABELORD_REPO, 'Testing', 'aaaxxx')

    assert err.value.status_code == 422
    assert err.value.message == 'Validation Failed'


def test_create_label_for_unexisting_repo(github):
    with pytest.raises(GitHubError) as err:
        github.create_label(UNEXISTING_REPO, 'Testing', 'aaaaaa')

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'


def test_create_label_with_bad_token(github_bad_token):
    with pytest.raises(GitHubError) as err:
        github_bad_token.list_labels(LABELORD_REPO)

    assert err.value.status_code == 401
    assert err.value.message == 'Bad credentials'


def test_update_label_for_existing_repo(github):
    # Just matching with betamax
    github.update_label(LABELORD_REPO, 'Testing 2', 'ababab', 'Testing')


def test_update_label_that_doesnt_exist(github):
    with pytest.raises(GitHubError) as err:
        github.update_label(LABELORD_REPO, 'Testing', 'aaaaaa')

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'


def test_update_label_with_weird_color(github):
    with pytest.raises(GitHubError) as err:
        github.update_label(LABELORD_REPO, 'Testing 2', 'aaaxxx')

    assert err.value.status_code == 422
    assert err.value.message == 'Validation Failed'


def test_update_label_for_unexisting_repo(github):
    with pytest.raises(GitHubError) as err:
        github.update_label(UNEXISTING_REPO, 'Testing 2', 'aaaaaa')

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'


def test_delete_label_for_existing_repo(github):
    # Just matching with betamax
    github.delete_label(LABELORD_REPO, 'Testing 2')


def test_delete_label_that_doesnt_exist(github):
    with pytest.raises(GitHubError) as err:
        github.delete_label(LABELORD_REPO, 'Testing')

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'


def test_delete_label_for_unexisting_repo(github):
    with pytest.raises(GitHubError) as err:
        github.delete_label(UNEXISTING_REPO, 'Testing 2')

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'


def test_error_properties(github):
    with pytest.raises(GitHubError) as err:
        github.delete_label(UNEXISTING_REPO, 'Testing 2')

    assert err.value.status_code == 404
    assert err.value.message == 'Not Found'
    assert err.value.code_message == '404 - Not Found'
    assert str(err.value) == 'GitHub: ERROR 404 - Not Found'


@pytest.mark.parametrize(
    ('data', 'signature', 'secret', 'encoding'),
    [
        ('{"data": "thisData"}'.encode('utf-8'),
         'sha1=ff00f668ad2b48568d5c72c01bd9b3b3c12032d6', 'key1', 'utf-8'),
        ('someMoreDataAsUTF8String'.encode('utf-8'),
         'sha1=7badf000d5b4eedfc0f40e7fe29c3f660849e081', 'key1', 'utf-8'),
        ('{"data": "thisData"}'.encode('utf-8'),
         'sha1=054ffbba526d7e94e1c9f99b6b33993dbd39b6c3', 'key2', 'utf-8'),
        ('someMoreDataAsUTF8String'.encode('utf-8'),
         'sha1=467a48608419b56e5ada01496baf4b12ef632304', 'key2', 'utf-8'),
        (''.encode('utf-8'),
         'sha1=94a32c46d6a6ea7b9af8d0a4d134a9028d6e3124', 'key2', 'utf-8'),
        ('someMoreDataAsCP1250String'.encode('cp1250'),
         'sha1=993fc6ccf9fa1cfd650825d886d5343549448e52', 'key1', 'cp1250'),
        ('{"data": "thisData"}'.encode('cp1250'),
         'sha1=054ffbba526d7e94e1c9f99b6b33993dbd39b6c3', 'key2', 'cp1250'),
    ]
)
def test_verify_webhook_signature_correct(data, signature, secret, encoding):
    assert GitHub.webhook_verify_signature(data, signature, secret, encoding)

# TODO: test multipage repos/labels
