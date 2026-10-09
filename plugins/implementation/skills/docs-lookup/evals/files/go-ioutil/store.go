package fetcher

import "io/ioutil"

// Save writes data to path.
func Save(path string, data []byte) error {
	return ioutil.WriteFile(path, data, 0o644)
}
