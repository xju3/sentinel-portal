Component({
  properties: {
    item: {
      type: Object,
      value: {},
    },
  },
  methods: {
    onTap() {
      this.triggerEvent('click', this.data.item)
    },
    onFavoriteTap() {
      this.triggerEvent('favorite', this.data.item)
    },
  },
})
