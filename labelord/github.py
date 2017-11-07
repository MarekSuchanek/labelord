import hashlib
import hmac
import requests


class GitHubError(Exception):

    def __init__(self, response):
        self.status_code = response.status_code
        self.message = response.json().get('message', 'No message provided')

    def __str__(self):
        return 'GitHub: ERROR {}'.format(self.code_message)

    @property
    def code_message(self, sep=' - '):
        return sep.join([str(self.status_code), self.message])


class GitHub:
    GH_API_ENDPOINT = 'https://api.github.com'

    def __init__(self, token, session=None):
        self.token = token
        self.set_session(session)

    def set_session(self, session):
        self.session = session or requests.Session()
        self.session.auth = self._session_auth()

    def _session_auth(self):
        def github_auth(req):
            req.headers = {
                'Authorization': 'token ' + self.token,
                'User-Agent': 'Python/Labelord'
            }
            return req
        return github_auth

    def _get_raising(self, url, expected_code=200):
        response = self.session.get(url)
        if response.status_code != expected_code:
            raise GitHubError(response)
        return response

    def _get_all_data(self, resource):
        """Get all data spread across multiple pages"""
        response = self._get_raising('{}{}?per_page=100&page=1'.format(
            self.GH_API_ENDPOINT, resource
        ))
        yield from response.json()
        while 'next' in response.links:
            response = self._get_raising(response.links['next']['url'])
            yield from response.json()

    def list_repositories(self):
        """Get list of names of accessible repositories (including owner)"""
        data = self._get_all_data('/user/repos')
        return [repo['full_name'] for repo in data]

    def list_labels(self, repository):
        """Get dict of labels with colors for given repository slug"""
        data = self._get_all_data('/repos/{}/labels'.format(repository))
        return {l['name']: str(l['color']) for l in data}

    def create_label(self, repository, name, color, **kwargs):
        """Create new label in given repository"""
        data = {'name': name, 'color': color}
        response = self.session.post(
            '{}/repos/{}/labels'.format(self.GH_API_ENDPOINT, repository),
            json=data
        )
        if response.status_code != 201:
            raise GitHubError(response)

    def update_label(self, repository, name, color, old_name=None, **kwargs):
        """Update existing label in given repository"""
        data = {'name': name, 'color': color}
        response = self.session.patch(
            '{}/repos/{}/labels/{}'.format(
                self.GH_API_ENDPOINT, repository, old_name or name
            ),
            json=data
        )
        if response.status_code != 200:
            raise GitHubError(response)

    def delete_label(self, repository, name, **kwargs):
        """Delete existing label in given repository"""
        response = self.session.delete(
             '{}/repos/{}/labels/{}'.format(
                 self.GH_API_ENDPOINT, repository, name
             )
        )
        if response.status_code != 204:
            raise GitHubError(response)

    @staticmethod
    def webhook_verify_signature(data, signature, secret, encoding='utf-8'):
        h = hmac.new(secret.encode(encoding), data, hashlib.sha1)
        return hmac.compare_digest('sha1=' + h.hexdigest(), signature)
