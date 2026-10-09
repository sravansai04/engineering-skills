package fetcher

import (
	"io/ioutil"
	"net/http"
)

// Fetch returns the body of url.
func Fetch(url string) ([]byte, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	return ioutil.ReadAll(resp.Body)
}
